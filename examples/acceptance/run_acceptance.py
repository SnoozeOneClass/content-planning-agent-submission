"""Independent acceptance probe; does not modify application code or old evidence.

Run from repository root: python -X utf8 examples/acceptance/run_acceptance.py
No API credentials are loaded and no new model API calls are made.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.agent import Agent
from src.domain import Rates, load_materials, read_json
from src.model import MockModel
from src.storage import Store

OUT = ROOT / "examples/acceptance"
WORK = ROOT / "runtime" / ("acceptance-" + uuid.uuid4().hex)
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "MODEL_API_KEY": ""}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command(arguments, name):
    completed = subprocess.run([sys.executable, "-X", "utf8", *arguments], cwd=ROOT, env=ENV,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
    stdout = OUT / (name + ".stdout.txt")
    stderr = OUT / (name + ".stderr.txt")
    stdout.write_text(completed.stdout, encoding="utf-8")
    stderr.write_text(completed.stderr, encoding="utf-8")
    return completed, {"command": ["python", "-X", "utf8", *arguments],
                       "exit_code": completed.returncode,
                       "stdout": stdout.relative_to(ROOT).as_posix(),
                       "stderr": stderr.relative_to(ROOT).as_posix()}


def check_trace(result):
    """Recompute the accepted tariff directly, independent of Rates.quote."""
    total_cost = total_duration = 0
    selected = {}
    failures = []
    for step in result.get("steps", []):
        action, observation = step["action"], step["result"]
        status = observation["status"]
        expected = (0, 0)
        if status in {"succeeded", "failed"} and action != "model_request":
            if action == "search_materials":
                expected = (2, 5)
            elif action == "estimate_plan":
                expected = (0, 1)
                if status == "succeeded":
                    selected = {p["step_id"]: list(dict.fromkeys(p["material_ids"])) for p in step["arguments"]["scripts"]}
            elif action == "generate_script":
                n = len(selected[step["arguments"]["step_id"]])
                expected = (2 + 2 * n, 10 + 5 * n)
            elif action == "save_plan":
                expected = (0, 2)
        charged = observation.get("charged", {"cost": 0, "duration": 0})
        if (charged["cost"], charged["duration"]) != expected:
            failures.append({"step": step["step"], "expected": expected, "charged": charged})
        total_cost += charged["cost"]
        total_duration += charged["duration"]
        if "spent_after" in step and step["spent_after"] != {"cost": total_cost, "duration": total_duration}:
            failures.append({"step": step["step"], "issue": "running ledger mismatch"})
    if result.get("spent") != {"cost": total_cost, "duration": total_duration}:
        failures.append({"issue": "final ledger mismatch"})
    request = result.get("request", {})
    if request and (total_cost > request["budget"] or total_duration > request["time_budget"]):
        failures.append({"issue": "constraint exceeded"})
    for script in result.get("scripts", []):
        allowed = set(script["material_ids"])
        for scene in script["scenes"]:
            if not set(scene["material_ids"]).issubset(allowed):
                failures.append({"issue": "invalid source reference", "script": script["step_id"]})
    return {"passed": not failures, "recomputed_cost": total_cost,
            "recomputed_duration": total_duration, "issues": failures}


class ActionSequence(MockModel):
    """A protocol stub for independent engine boundary tests, never LLM evidence."""
    def __init__(self, actions):
        self.actions = iter(actions)

    def decide(self, state, rates):
        name, args = next(self.actions, ("finish", {"message": "acceptance probe stopped"}))
        return self.decision(name, args, "独立验收的协议替身动作")


def one_script_actions(ids):
    return [("search_materials", {"query": "字幕功能"}),
            ("estimate_plan", {"scripts": [{"step_id": "S1", "material_ids": ids, "brief": "字幕功能介绍"}]}),
            ("generate_script", {"step_id": "S1"}),
            ("save_plan", {"title": "字幕功能介绍", "summary": "依资料生成的内容方案"})]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True)
    log = {"baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
           "started_at": datetime.now(timezone.utc).isoformat(),
           "work_dir": WORK.relative_to(ROOT).as_posix(), "commands": [], "cli": [], "boundary": [], "real_evidence": []}
    tests, entry = command(["-m", "unittest", "discover", "-s", "tests", "-v"], "unit-tests")
    log["commands"].append(entry)
    log["unit_tests_passed"] = tests.returncode == 0

    cases = [
        ("normal", None, [False], "completed"),
        ("replan", None, [False], "completed"),
        ("missing-budget", None, [False], "needs_input"),
        ("missing-time", None, [False], "needs_input"),
        ("tool-failure", "generate-once", [False], "completed"),
        ("save-failure", "save-always", [False], "incomplete"),
        ("over-budget", None, [False], "incomplete"),
        ("out-of-time", None, [False], "incomplete"),
        ("no-materials", None, [False], "incomplete"),
        ("repeat", None, [False, False], "completed"),
        ("partial-resume", "second-script", [False, True], "completed"),
        ("step-limit", None, [False], "incomplete"),
    ]
    for name, fault, resumes, expected in cases:
        outputs = []
        db = WORK / (name + ".sqlite3")
        for index, resume in enumerate(resumes, 1):
            output = OUT / "cli" / f"{name}-{index}.json"
            args = ["-m", "src.main", "--input", f"examples/inputs/{name}.json", "--mode", "mock",
                    "--db", db.relative_to(ROOT).as_posix(), "--env-file", "runtime/acceptance-no-env",
                    "--output", output.relative_to(ROOT).as_posix()]
            if fault:
                args += ["--faults", f"examples/faults/{fault}.json"]
            if resume:
                args += ["--resume"]
            if name == "step-limit":
                args += ["--max-steps", "1"]
            run, entry = command(args, f"cli-{name}-{index}")
            log["commands"].append(entry)
            result = json.loads(run.stdout)
            outputs.append(result)
            check = check_trace(result)
            log["cli"].append({"case": name, "run": index, "status": result["status"],
                               "exit_code": run.returncode, "replayed": result["replayed"],
                               "output": output.relative_to(ROOT).as_posix(), "ledger": check})
        store = Store(db)
        row_count = store.db.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
        store.close()
        expected_rows = 1 if expected == "completed" else 0
        log["cli"][-1]["expected_status_passed"] = outputs[-1]["status"] == expected
        log["cli"][-1]["saved_rows_passed"] = row_count == expected_rows
        log["cli"][-1]["saved_rows"] = row_count
        if name == "repeat":
            log["cli"][-1]["deduplication_passed"] = (outputs[1]["replayed"] and outputs[0]["spent"] == outputs[1]["spent"] and outputs[0]["steps"] == outputs[1]["steps"])
        if name == "partial-resume":
            log["cli"][-1]["partial_preservation_passed"] = (outputs[0]["status"] == "incomplete" and len(outputs[0]["scripts"]) == 1 and outputs[0]["scripts"][0] in outputs[1]["scripts"])

    materials, rates = load_materials(ROOT / "data/materials.json"), Rates()
    probes = [
        ("exact-boundary", 6, 23, ["M01"], {}, "completed", (6, 23)),
        ("time-one-short", 6, 22, ["M01"], {}, "incomplete", (2, 6)),
        ("budget-one-short", 5, 23, ["M01"], {}, "incomplete", (2, 6)),
        ("duplicate-id", 6, 23, ["M01", "M01"], {}, "completed", (6, 23)),
        ("save-fails-at-deadline", 6, 23, ["M01"], {"save_plan": {"at_calls": [1], "retryable": True}}, "incomplete", (6, 23)),
    ]
    for name, budget, duration, ids, faults, expected, totals in probes:
        store = Store(WORK / (name + ".sqlite3"))
        actions = one_script_actions(ids)
        if name == "save-fails-at-deadline":
            actions.append(("save_plan", {"title": "重试保存", "summary": "保留脚本"}))
        result = Agent(ActionSequence(actions), store, materials, rates, faults=faults).run({"request_id": name, "topic": "字幕功能", "budget": budget, "time_budget": duration})
        rows = store.db.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
        store.close()
        save(OUT / "boundary" / (name + ".json"), result)
        log["boundary"].append({"case": name, "status": result["status"], "spent": result["spent"],
                                "saved_rows": rows, "ledger": check_trace(result),
                                "passed": result["status"] == expected and tuple(result["spent"][k] for k in ("cost", "duration")) == totals and rows == int(expected == "completed")})

    # Review stored real records without executing model calls or loading .env.
    for path in sorted((ROOT / "examples/real").glob("*.output.json")):
        payload = read_json(path)
        for number, result in enumerate(payload["runs"], 1):
            receipts = [s.get("model_receipt", {}) for s in result.get("steps", []) if s.get("source") == "real_model"]
            record = {"case": path.stem, "run": number, "status": result["status"],
                      "mode": result["mode"], "ledger": check_trace(result),
                      "recorded_model_decisions": len(receipts),
                      "response_ids_present": all(r.get("response_id") and r.get("tool_call_id") for r in receipts),
                      "actions": [s["action"] for s in result.get("steps", [])]}
            log["real_evidence"].append(record)
    log["finished_at"] = datetime.now(timezone.utc).isoformat()
    log["all_checks_passed"] = (log["unit_tests_passed"] and
        all(c["exit_code"] == 0 and c["ledger"]["passed"] and all(v for k, v in c.items() if k.endswith("_passed")) for c in log["cli"]) and
        all(c["passed"] and c["ledger"]["passed"] for c in log["boundary"]) and
        all(c["ledger"]["passed"] and c["response_ids_present"] and c["mode"] == "real" for c in log["real_evidence"]))
    save(OUT / "results.json", log)
    print(json.dumps({"all_checks_passed": log["all_checks_passed"], "cli_runs": len(log["cli"]),
                      "boundary_cases": len(log["boundary"]), "real_records_checked": len(log["real_evidence"]),
                      "results": "examples/acceptance/results.json"}, ensure_ascii=False, indent=2))
    return 0 if log["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
