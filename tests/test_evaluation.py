import io
import json
import shutil
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from src.agent import Agent
from src.domain import ROOT, InputError, Rates, load_materials
from src.evaluate import CASES, inspect_case, main as evaluate_main, resolve_output_directory
from src.model import MockModel, ModelError
from src.storage import Store
from tests.test_agent import ScriptedModel


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = ROOT / "runtime/tests" / uuid.uuid4().hex
        self.temp.mkdir(parents=True)
        self.store = Store(self.temp / "test.sqlite3")
        self.materials = load_materials(ROOT / "data/materials.json")
        self.request = {"request_id": "no-materials", "topic": "火星地质勘探", "budget": 20, "time_budget": 100}

    def tearDown(self):
        self.store.close()
        assert self.temp.resolve().is_relative_to((ROOT / "runtime/tests").resolve())
        shutil.rmtree(self.temp)

    def run_agent(self, model):
        return Agent(model, self.store, self.materials, Rates()).run(self.request)

    def test_no_materials_requires_successful_empty_search(self):
        r = self.run_agent(MockModel())
        checks = inspect_case("no-materials", [r], None)
        self.assertTrue(all(checks.values()))
        self.assertTrue(checks["empty_search_observed"])

    def test_model_outage_is_not_a_passing_no_materials_case(self):
        class Unavailable(MockModel):
            def decide(self, *args):
                raise ModelError("controlled model outage")
        r = self.run_agent(Unavailable())
        checks = inspect_case("no-materials", [r], None)
        self.assertFalse(checks["empty_search_observed"])
        self.assertFalse(checks["no_materials_stopped_by_model"])
        self.assertFalse(all(checks.values()))

    def test_model_outage_after_empty_search_still_fails_case(self):
        class SearchThenOutage(MockModel):
            def decide(self, state, rates):
                if state["trace"]:
                    raise ModelError("controlled model outage")
                return self.decision("search_materials", {"query": "火星地质勘探"}, "查询资料")
        r = self.run_agent(SearchThenOutage())
        checks = inspect_case("no-materials", [r], None)
        self.assertTrue(checks["empty_search_observed"])
        self.assertFalse(checks["no_materials_stopped_by_model"])

    def test_found_materials_do_not_pass_no_materials_case(self):
        r = self.run_agent(ScriptedModel([("search_materials", {"query": "字幕功能"}), ("finish", {"message": "停止"})]))
        self.assertFalse(inspect_case("no-materials", [r], None)["empty_search_observed"])

    def test_query_refinement_can_end_with_an_empty_search(self):
        r = self.run_agent(ScriptedModel([("search_materials", {"query": "字幕功能"}),
                                         ("search_materials", {"query": "火星地质勘探"}),
                                         ("finish", {"message": "没有对应主题资料"})]))
        self.assertTrue(all(inspect_case("no-materials", [r], None).values()))

    def test_selected_cases_default_to_a_separate_unique_directory(self):
        first = resolve_output_directory("real", ["normal"], root=self.temp)
        second = resolve_output_directory("real", ["normal"], root=self.temp)
        self.assertTrue(first.is_relative_to(self.temp / "runtime/evaluations"))
        self.assertNotEqual(first, second)
        self.assertEqual(resolve_output_directory("real", root=self.temp), self.temp / "examples/real")

    def test_partial_cli_does_not_overwrite_existing_full_index(self):
        out = self.temp / "report"
        out.mkdir()
        full = {"mode": "mock", "total": 12, "cases": [{"case": name} for name in CASES]}
        path = out / "results.json"
        path.write_text(json.dumps(full), encoding="utf-8")
        before = path.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            evaluate_main(["--mode", "mock", "--case", "normal", "--out", str(out), "--env-file", str(self.temp / "no-env")])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((out / "normal.output.json").exists())

    def test_partial_run_cannot_use_canonical_report_directory(self):
        for mode in ("real", "mock"):
            with self.subTest(mode=mode), self.assertRaises(InputError):
                resolve_output_directory(mode, ["normal"], self.temp / "examples" / mode, root=self.temp)

    def test_same_selected_cases_can_refresh_their_own_directory(self):
        out = self.temp / "smoke"
        out.mkdir()
        (out / "results.json").write_text(json.dumps({"mode": "mock", "cases": [{"case": "normal"}]}), encoding="utf-8")
        self.assertEqual(resolve_output_directory("mock", ["normal"], out, root=self.temp), out)


if __name__ == "__main__":
    unittest.main()
