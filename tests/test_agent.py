import copy
import json
import shutil
import unittest
import uuid
from pathlib import Path

from src.agent import Agent
from src.domain import ROOT, InputError, Rates, load_materials, read_json, validate_request
from src.model import MockModel, ModelError
from src.storage import BusyError, Store, execution_lock


class ScriptedModel(MockModel):
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def decide(self, state, rates):
        action, arguments = next(self.decisions, ("finish", {"message": "test stop"}))
        return self.decision(action, arguments, "测试协议动作")


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = ROOT / "runtime" / "tests" / uuid.uuid4().hex
        self.temp.mkdir(parents=True)
        self.store = Store(self.temp / "test.sqlite3")
        self.materials = load_materials(ROOT / "data/materials.json")
        self.rates = Rates()

    def tearDown(self):
        self.store.close()
        assert self.temp.resolve().is_relative_to((ROOT / "runtime" / "tests").resolve())
        shutil.rmtree(self.temp)

    def run_case(self, name, **options):
        model = options.pop("model", MockModel())
        resume = options.pop("resume", False)
        return Agent(model, self.store, self.materials, self.rates, **options).run(read_json(ROOT / f"examples/inputs/{name}.json"), resume=resume)

    def assert_accounting(self, result):
        charged = [s["result"].get("charged", {}) for s in result["steps"]]
        self.assertEqual(result["spent"]["cost"], sum(c.get("cost", 0) for c in charged))
        self.assertEqual(result["spent"]["duration"], sum(c.get("duration", 0) for c in charged))
        self.assertGreaterEqual(result["remaining"]["budget"], 0)
        self.assertGreaterEqual(result["remaining"]["time_budget"], 0)

    def test_normal_saved_result_is_actual_database_record(self):
        r = self.run_case("normal")
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["saved_plan"], self.store.get_plan("normal"))
        self.assertEqual(r["spent"], {"cost": 12, "duration": 38})
        self.assertEqual(r["task_plan"][0]["status"], "succeeded")
        self.assert_accounting(r)

    def test_replanning_observes_estimate_and_changes_selection(self):
        r = self.run_case("replan")
        self.assertEqual(r["status"], "completed")
        quotes = [s for s in r["steps"] if s["action"] == "estimate_plan"]
        self.assertEqual([q["result"]["data"]["feasible"] for q in quotes], [False, True])
        self.assertEqual([len(q["arguments"]["scripts"][0]["material_ids"]) for q in quotes], [4, 2])
        self.assertEqual(r["spent"], {"cost": 8, "duration": 29})
        self.assertEqual(quotes[0]["next_action"], "estimate_plan")
        self.assert_accounting(r)

    def test_missing_budget_and_time_do_not_call_model(self):
        class NeverModel(MockModel):
            def decide(self, *args):
                self.fail("must not call model")
        for name, missing in (("missing-budget", "budget"), ("missing-time", "time_budget")):
            r = self.run_case(name, model=NeverModel())
            self.assertEqual(r["status"], "needs_input")
            self.assertEqual(r["missing_fields"], [missing])
            self.assertEqual(r["spent"], {"cost": 0, "duration": 0})

    def test_invalid_numeric_input(self):
        for value in (-1, True, float("nan"), float("inf"), "10"):
            with self.subTest(value=value), self.assertRaises(InputError):
                validate_request({"topic": "字幕", "budget": value, "time_budget": 30})

    def test_zero_budget_is_not_missing(self):
        r = Agent(MockModel(), self.store, self.materials, self.rates, max_steps=3).run({"topic": "字幕", "budget": 0, "time_budget": 30})
        self.assertEqual(r["status"], "incomplete")
        self.assertEqual(r["spent"]["cost"], 0)
        self.assertNotIn("missing_fields", r)

    def test_budget_cannot_be_overrun_even_for_minimal_plan(self):
        r = self.run_case("over-budget")
        self.assertEqual(r["status"], "incomplete")
        self.assertIsNone(r["saved_plan"])
        self.assertEqual(r["reason"]["shortfall"]["budget"], 1)
        self.assert_accounting(r)

    def test_time_includes_estimates_and_mandatory_save(self):
        r = self.run_case("out-of-time")
        self.assertEqual(r["status"], "incomplete")
        self.assertIsNone(self.store.get_plan("out-of-time"))
        self.assertGreater(r["reason"]["shortfall"]["time_budget"], 0)
        self.assert_accounting(r)

    def test_temporary_failure_charges_attempt_and_keeps_search(self):
        r = self.run_case("tool-failure", faults=read_json(ROOT / "examples/faults/generate-once.json"))
        self.assertEqual(r["status"], "completed")
        attempts = [s for s in r["steps"] if s["action"] == "generate_script"]
        self.assertEqual([s["result"]["status"] for s in attempts], ["failed", "succeeded"])
        self.assertGreater(attempts[0]["result"]["charged"]["cost"], 0)
        self.assertEqual(sum(s["action"] == "search_materials" for s in r["steps"]), 1)
        self.assert_accounting(r)

    def test_save_failure_never_claims_success(self):
        r = self.run_case("save-failure", faults=read_json(ROOT / "examples/faults/save-always.json"))
        self.assertEqual(r["status"], "incomplete")
        self.assertEqual(len(r["scripts"]), 1)
        self.assertIsNone(r["saved_plan"])
        self.assertIsNone(self.store.get_plan("save-failure"))
        self.assert_accounting(r)

    def test_identical_request_deduplicated_across_instances(self):
        first = self.run_case("repeat")
        second = self.run_case("repeat")
        self.assertTrue(second["replayed"])
        self.assertEqual(first["saved_plan"], second["saved_plan"])
        self.assertEqual(first["spent"], second["spent"])
        self.assertEqual(first["steps"], second["steps"])
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM plans").fetchone()[0], 1)

    def test_implicit_request_id_deduplicates(self):
        raw = {"topic": "字幕功能推广", "budget": 20, "time_budget": 100}
        a = Agent(MockModel(), self.store, self.materials, self.rates)
        first, second = a.run(raw), a.run(raw)
        self.assertEqual(first["request_id"], second["request_id"])
        self.assertTrue(second["replayed"])

    def test_conflicting_request_id_does_not_overwrite(self):
        first = self.run_case("normal")
        raw = read_json(ROOT / "examples/inputs/normal.json")
        raw["budget"] = 21
        second = Agent(MockModel(), self.store, self.materials, self.rates).run(raw)
        self.assertEqual(second["reason"]["code"], "REQUEST_CONFLICT")
        self.assertEqual(first["saved_plan"], self.store.get_plan("normal"))

    def test_changed_materials_require_new_request_id(self):
        self.run_case("normal")
        self.materials["M01"]["content"] = "更新后的功能资料"
        r = self.run_case("normal")
        self.assertEqual(r["reason"]["code"], "REQUEST_CONFLICT")

    def test_partial_failure_resume_preserves_success_and_consumption(self):
        faults = read_json(ROOT / "examples/faults/second-script.json")
        first = self.run_case("partial-resume", faults=faults)
        self.assertEqual(first["status"], "incomplete")
        self.assertEqual(len(first["scripts"]), 1)
        prior_script = copy.deepcopy(first["scripts"][0])
        second = self.run_case("partial-resume", faults=faults, resume=True)
        self.assertEqual(second["status"], "completed")
        self.assertIn(prior_script, second["scripts"])
        script_1_calls = [s for s in second["steps"] if s["action"] == "generate_script" and s["arguments"]["step_id"] == "script_1"]
        self.assertEqual(len(script_1_calls), 1)
        self.assertGreater(second["spent"]["cost"], first["spent"]["cost"])
        self.assert_accounting(second)

    def test_step_limit_is_explicit_and_resume_does_not_reset_it(self):
        r = self.run_case("step-limit", max_steps=1)
        self.assertEqual(r["reason"]["code"], "STEP_LIMIT")
        again = self.run_case("step-limit", max_steps=1, resume=True)
        self.assertEqual(again["spent"], r["spent"])
        self.assertEqual(again["reason"]["code"], "STEP_LIMIT")

    def test_invalid_actions_are_also_bounded(self):
        decisions = [("invented_tool", {})] * 5
        r = self.run_case("normal", model=ScriptedModel(decisions), max_steps=3)
        self.assertEqual(r["reason"]["code"], "STEP_LIMIT")
        self.assertEqual(r["spent"], {"cost": 0, "duration": 0})

    def test_model_unavailable_does_not_fallback_silently(self):
        class Unavailable(MockModel):
            mode = "real"
            def decide(self, *args):
                raise ModelError("test connection unavailable")
        r = self.run_case("normal", model=Unavailable())
        self.assertEqual(r["mode"], "real")
        self.assertEqual(r["reason"]["code"], "MODEL_ERROR")
        self.assertIsNone(r["saved_plan"])

    def test_save_before_generation_is_rejected(self):
        r = self.run_case("normal", model=ScriptedModel([("save_plan", {"title": "bad", "summary": "bad"})]))
        self.assertEqual(r["steps"][0]["result"]["error"]["code"], "DEPENDENCY_NOT_READY")
        self.assertIsNone(r["saved_plan"])

    def test_duplicate_material_ids_count_once(self):
        plan = [{"step_id": "s1", "material_ids": ["M01", "M01", "M02"], "brief": "字幕功能介绍"}]
        model = ScriptedModel([("search_materials", {"query": "字幕功能"}), ("estimate_plan", {"scripts": plan}),
                               ("generate_script", {"step_id": "s1"}), ("save_plan", {"title": "字幕", "summary": "功能介绍"})])
        r = self.run_case("normal", model=model)
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["spent"], {"cost": 8, "duration": 28})
        self.assertEqual(r["scripts"][0]["material_ids"], ["M01", "M02"])

    def test_unknown_materials_not_executed(self):
        plan = [{"step_id": "s1", "material_ids": ["M99"], "brief": "介绍"}]
        r = self.run_case("normal", model=ScriptedModel([("estimate_plan", {"scripts": plan})]))
        self.assertEqual(r["steps"][0]["result"]["error"]["code"], "INVALID_ARGUMENTS")
        self.assertEqual(r["spent"]["cost"], 0)

    def test_generated_script_references_must_be_supplied(self):
        with self.assertRaises(InputError):
            Agent.validate_script({"title": "bad", "scenes": [{"visual": "x", "narration": "y", "material_ids": ["M99"]}]}, ["M01"])

    def test_no_materials_returns_incomplete(self):
        r = self.run_case("no-materials")
        self.assertEqual(r["status"], "incomplete")
        self.assertEqual(r["scripts"], [])

    def test_retrieval_changes_with_document_content(self):
        a = Agent(MockModel(), self.store, self.materials, self.rates)
        self.assertEqual(a.search("火星地质"), [])
        self.materials["M01"]["topic"] = "火星地质"
        self.assertEqual(a.search("火星地质")[0]["material_id"], "M01")

    def test_lock_prevents_duplicate_concurrent_execution(self):
        with execution_lock(self.store.path), self.assertRaises(BusyError):
            self.run_case("normal")

    def test_generated_success_is_cached_without_additional_charge(self):
        plan = [{"step_id": "s1", "material_ids": ["M01"], "brief": "字幕介绍"}]
        actions = [("search_materials", {"query": "字幕功能"}), ("estimate_plan", {"scripts": plan}),
                   ("generate_script", {"step_id": "s1"}), ("generate_script", {"step_id": "s1"}),
                   ("save_plan", {"title": "字幕", "summary": "介绍字幕"})]
        r = self.run_case("normal", model=ScriptedModel(actions))
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["steps"][3]["result"]["status"], "cached")
        self.assertEqual(r["spent"], {"cost": 6, "duration": 23})

    def test_replanning_cannot_remove_or_rewrite_a_successful_script(self):
        plan = [{"step_id": "s1", "material_ids": ["M01"], "brief": "字幕介绍"}]
        changed = [{"step_id": "s1", "material_ids": ["M02"], "brief": "修改已完成步骤"}]
        actions = [("search_materials", {"query": "字幕功能"}), ("estimate_plan", {"scripts": plan}),
                   ("generate_script", {"step_id": "s1"}), ("estimate_plan", {"scripts": changed}),
                   ("save_plan", {"title": "字幕", "summary": "保留已完成结果"})]
        r = self.run_case("normal", model=ScriptedModel(actions))
        self.assertEqual(r["steps"][3]["result"]["error"]["code"], "INVALID_ARGUMENTS")
        self.assertEqual(r["scripts"][0]["material_ids"], ["M01"])
        self.assertEqual(r["status"], "completed")

    def test_failure_invalidates_previous_budget_feasibility(self):
        plan = [{"step_id": "s1", "material_ids": ["M01", "M02", "M03", "M04"], "brief": "字幕介绍"}]
        actions = [("search_materials", {"query": "字幕功能"}), ("estimate_plan", {"scripts": plan}),
                   ("generate_script", {"step_id": "s1"}), ("generate_script", {"step_id": "s1"})]
        agent = Agent(ScriptedModel(actions), self.store, self.materials, self.rates,
                      faults={"generate_script": {"at_calls": [1]}})
        r = agent.run({"topic": "字幕功能推广", "budget": 12, "time_budget": 100})
        self.assertEqual(r["steps"][2]["result"]["status"], "failed")
        self.assertEqual(r["steps"][3]["result"]["error"]["code"], "CONSTRAINT_BLOCKED")
        self.assertEqual(r["spent"]["cost"], 12)
        self.assertIsNone(r["saved_plan"])

    def test_checkpoint_survives_reopening_database(self):
        first = self.run_case("normal")
        path = self.store.path
        self.store.close()
        self.store = Store(path)
        second = self.run_case("normal")
        self.assertTrue(second["replayed"])
        self.assertEqual(second["saved_plan"], first["saved_plan"])

    def test_finish_recalculates_shortfall_after_another_search(self):
        plan = [{"step_id": "S1", "material_ids": ["M01", "M02", "M03", "M04"], "brief": "字幕介绍"}]
        actions = [("search_materials", {"query": "字幕功能"}), ("estimate_plan", {"scripts": plan}),
                   ("search_materials", {"query": "字幕时间"}), ("finish", {"message": "停止当前计划"})]
        agent = Agent(ScriptedModel(actions), self.store, self.materials, self.rates)
        r = agent.run({"topic": "字幕功能推广", "budget": 10, "time_budget": 30})
        self.assertEqual(r["spent"], {"cost": 4, "duration": 11})
        self.assertEqual(r["reason"]["shortfall"], {"budget": 4, "time_budget": 13})
        self.assertEqual(r["steps"][1]["result"]["data"]["shortfall"], {"budget": 2, "time_budget": 8})
        self.assertEqual(r["plan_revisions"][0]["estimate"]["shortfall"], {"budget": 2, "time_budget": 8})
        self.assert_accounting(r)

    def test_finish_reports_new_shortfall_after_feasible_plan_fails(self):
        plan = [{"step_id": "S1", "material_ids": ["M01", "M02", "M03", "M04"], "brief": "字幕介绍"}]
        actions = [("search_materials", {"query": "字幕功能"}), ("estimate_plan", {"scripts": plan}),
                   ("generate_script", {"step_id": "S1"}), ("finish", {"message": "失败后停止"})]
        agent = Agent(ScriptedModel(actions), self.store, self.materials, self.rates,
                      faults={"generate_script": {"at_calls": [1]}})
        r = agent.run({"topic": "字幕功能推广", "budget": 12, "time_budget": 100})
        self.assertTrue(r["plan_revisions"][0]["estimate"]["feasible"])
        self.assertEqual(r["reason"]["shortfall"], {"budget": 10, "time_budget": 0})
        self.assertEqual(r["spent"], {"cost": 12, "duration": 36})
        self.assert_accounting(r)


if __name__ == "__main__":
    unittest.main()
