"""Run actual cases and export outputs, traces, assertions and an evidence index."""

from __future__ import annotations

import argparse
import copy
import json
import platform
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .agent import Agent
from .domain import ROOT, InputError, Rates, canonical, digest, load_materials, read_json
from .model import ChatModel, MockModel, load_env
from .storage import Store

CASES = {
    "normal": {"statuses": ["completed"]},
    "replan": {"statuses": ["completed"]},
    "missing-budget": {"statuses": ["needs_input"], "missing": "budget"},
    "missing-time": {"statuses": ["needs_input"], "missing": "time_budget"},
    "tool-failure": {"statuses": ["completed", "incomplete"], "faults": "generate-once", "requires_failure": True},
    "save-failure": {"statuses": ["incomplete"], "faults": "save-always", "requires_failure": True, "keep_script": True},
    "over-budget": {"statuses": ["incomplete"], "shortfall": "budget"},
    "out-of-time": {"statuses": ["incomplete"], "shortfall": "time_budget"},
    "no-materials": {"statuses": ["incomplete"], "requires_empty_search": True},
    "repeat": {"statuses": ["completed"], "repeat": True},
    "partial-resume": {"statuses": ["completed"], "faults": "second-script", "resume": True, "requires_failure": True},
    "step-limit": {"statuses": ["incomplete"], "max_steps": 1},
}


UNVERIFIED_DATABASE = object()


def inspect_case(name, runs, db_plan=UNVERIFIED_DATABASE):
    spec, result = CASES[name], runs[-1]
    checks = {}

    def check(label, condition):
        checks[label] = bool(condition)

    check("expected_status", result["status"] in spec["statuses"])
    steps = result.get("steps", [])
    charged = [s["result"].get("charged", {}) for s in steps]
    check("cost_ledger", result["spent"]["cost"] == sum(c.get("cost", 0) for c in charged))
    check("duration_ledger", result["spent"]["duration"] == sum(c.get("duration", 0) for c in charged))
    if result.get("remaining"):
        check("within_budget", result["remaining"]["budget"] >= 0)
        check("within_time", result["remaining"]["time_budget"] >= 0)
    if db_plan is not UNVERIFIED_DATABASE:
        check("database_matches_saved_result", result.get("saved_plan") == db_plan)
    check("completion_requires_saved_plan", result["status"] != "completed" or result.get("saved_plan") is not None)
    if result["status"] == "completed":
        check("required_script_count", len(result["scripts"]) == result["request"]["script_count"])
        check("generated_text_present", all(s.get("scenes") and all(x.get("narration") for x in s["scenes"]) for s in result["scripts"]))
    if result["status"] == "incomplete":
        check("unfinished_reason_present", bool(result.get("reason", {}).get("message")))
    if spec.get("missing"):
        check("missing_field_identified", spec["missing"] in result.get("missing_fields", []))
        check("missing_input_no_actions", not steps)
    if spec.get("requires_empty_search"):
        searches = [s["result"] for s in steps if s.get("action") == "search_materials" and s["result"].get("status") == "succeeded"]
        check("empty_search_observed", any(s.get("data") == [] for s in searches))
        check("no_materials_no_scripts", result.get("scripts") == [])
        check("no_materials_not_saved", result.get("saved_plan") is None)
        check("no_materials_stopped_by_model", (result.get("reason") or {}).get("code") == "MODEL_STOPPED"
              and bool(steps) and steps[-1].get("action") == "finish")
    if spec.get("requires_failure"):
        check("failure_observed", any(s["result"].get("error", {}).get("code") == "INJECTED_TOOL_FAILURE" for s in steps if s["result"].get("error")))
    if spec.get("keep_script"):
        check("successful_script_preserved", len(result["scripts"]) == 1)
        check("save_failure_not_saved", result.get("saved_plan") is None)
    if spec.get("shortfall"):
        check("shortfall_reported", result.get("reason", {}).get("shortfall", {}).get(spec["shortfall"], 0) > 0)
    if name == "step-limit":
        check("explicit_step_limit", result.get("reason", {}).get("code") == "STEP_LIMIT")
    if spec.get("repeat"):
        check("duplicate_returns_cache", result["replayed"])
        check("duplicate_no_new_consumption", runs[0]["spent"] == result["spent"])
        check("duplicate_same_plan", runs[0]["saved_plan"] == result["saved_plan"])
        check("duplicate_no_new_steps", runs[0]["steps"] == result["steps"])
    if spec.get("resume"):
        check("partial_success_before_resume", runs[0]["status"] == "incomplete" and len(runs[0]["scripts"]) == 1)
        check("resume_keeps_success", all(s in result["scripts"] for s in runs[0]["scripts"]))
        ids = {s["step_id"] for s in runs[0]["scripts"]}
        check("resume_does_not_regenerate_success", not any(s.get("action") == "generate_script" and s.get("arguments", {}).get("step_id") in ids for s in steps[len(runs[0]["steps"]):]))
    return checks


def execution_metadata(result):
    """Derive path evidence from actual steps, not from a prewritten summary."""
    steps = result.get("steps", [])
    return {
        "actions": [s["action"] for s in steps],
        "replanning_observed": any(s.get("action") == "estimate_plan" and s["result"].get("data")
            and not s["result"]["data"].get("feasible", True) and s.get("next_action") == "estimate_plan" for s in steps),
        "failure_handling_observed": any(s["result"]["status"] == "failed" and s.get("next_action") not in {None, "end"} for s in steps),
        "real_model_responses": sum(bool(s.get("model_receipt", {}).get("response_id"))
            and s["model_receipt"].get("source") == "real_model" for s in steps),
    }


def resolve_output_directory(mode, selected_cases=None, output=None, *, root=ROOT):
    if output is not None:
        out = Path(output)
    elif selected_cases:
        out = root / "runtime" / "evaluations" / f"{mode}-selected-{uuid.uuid4().hex}"
    else:
        out = root / "examples" / mode
    if selected_cases:
        canonical_dirs = {(root / "examples" / m).resolve() for m in ("mock", "real")}
        if out.resolve() in canonical_dirs:
            raise InputError("部分用例请使用独立 --out 目录；examples/mock 和 examples/real 用于完整验收")
        summary_file = out / "results.json"
        if summary_file.exists():
            try:
                previous = read_json(summary_file)
                previous_cases = {case["case"] for case in previous["cases"]}
                if previous.get("mode") != mode or previous_cases - set(selected_cases):
                    raise InputError("输出目录已有其他模式或用例的结果，请指定新的 --out 目录以保留原汇总")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if isinstance(exc, InputError):
                    raise
                raise InputError("输出目录中的已有汇总无法解析，请指定新的 --out 目录") from None
    return out


def trace_markdown(name, runs):
    lines = [f"# {name} 执行记录", "", f"模式：{runs[-1]['mode']}", "", runs[-1].get("evidence_scope", "输入校验"), ""]
    for index, run in enumerate(runs, 1):
        lines += [f"## 第 {index} 次执行", "", f"状态：{run['status']}；累计费用：{run['spent']['cost']}；累计耗时：{run['spent']['duration']}；复用：{run['replayed']}", ""]
        for step in run.get("steps", []):
            lines += [f"### 步骤 {step['step']} {step['action']}", "", f"依据：{step.get('reason', '模型接口失败')}", "",
                      "参数：`" + canonical(step.get("arguments", {})).replace("`", "'") + "`", "",
                      "返回：" + step.get("observation_summary", canonical(step["result"])), "",
                      f"结果状态：{step['result']['status']}；本次消耗：`{canonical(step['result'].get('charged', {}))}`", "",
                      f"后续动作：{step.get('next_action', 'end')}；依据：{step.get('next_reason', '执行结束，最终状态以实际结果为准')}", ""]
        if run.get("reason"):
            lines += ["结束原因：" + canonical(run["reason"]), ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="执行验收用例并保存实际输出与 Trace")
    parser.add_argument("--mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--out", help="完整验收默认写 examples/<mode>；指定 --case 时默认写独立 runtime/evaluations 目录")
    parser.add_argument("--case", action="append", choices=tuple(CASES), help="可以重复指定；省略则全部执行")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        out = resolve_output_directory(args.mode, args.case, args.out)
    except InputError as exc:
        parser.error(str(exc))
    load_env(args.env_file)
    out.mkdir(parents=True, exist_ok=True)
    work = ROOT / "runtime" / "evaluations" / uuid.uuid4().hex
    work.mkdir(parents=True)
    materials, rates = load_materials(ROOT / "data/materials.json"), Rates()
    results = []
    try:
        for name in args.case or CASES:
            spec = CASES[name]
            request = read_json(ROOT / f"examples/inputs/{name}.json")
            faults = read_json(ROOT / f"examples/faults/{spec['faults']}.json") if spec.get("faults") else None
            store = Store(work / f"{name}.sqlite3")
            try:
                model = MockModel() if args.mode == "mock" else ChatModel()
                agent = Agent(model, store, materials, rates, max_steps=spec.get("max_steps", 16), faults=faults)
                runs = [copy.deepcopy(agent.run(request))]
                if spec.get("repeat"):
                    runs.append(copy.deepcopy(agent.run(request)))
                if spec.get("resume"):
                    runs.append(copy.deepcopy(agent.run(request, resume=True)))
                checks = inspect_case(name, runs, store.get_plan(request["request_id"]))
                result = {"case": name, "passed": all(checks.values()), "checks": checks, "status": runs[-1]["status"],
                          "spent": runs[-1]["spent"], **execution_metadata(runs[-1]),
                          "input": f"examples/inputs/{name}.json", "output": f"{name}.output.json", "trace": f"{name}.trace.md"}
                (out / f"{name}.output.json").write_text(json.dumps({"input": request, "runs": runs, "checks": checks}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (out / f"{name}.trace.md").write_text(trace_markdown(name, runs), encoding="utf-8")
                results.append(result)
                print(f"{name}: {'PASS' if result['passed'] else 'FAIL'} {result['status']} cost={result['spent']['cost']} duration={result['spent']['duration']}", flush=True)
            finally:
                store.close()
    finally:
        assert work.resolve().is_relative_to((ROOT / "runtime" / "evaluations").resolve())
        shutil.rmtree(work)
    summary = {"mode": args.mode, "run_scope": "selected" if args.case else "full",
               "generated_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
               "materials_sha256": digest(materials), "rates_sha256": digest(rates.data),
               "passed": sum(r["passed"] for r in results), "total": len(results), "cases": results,
               "evidence_scope": "真实模型运行" if args.mode == "real" else "离线 Mock 流程验证，不能证明真实模型决策效果"}
    (out / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {summary['passed']}/{summary['total']} -> {out / 'results.json'}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
