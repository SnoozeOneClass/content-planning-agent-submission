"""Read-only readiness check. Offline success alone never counts as real evidence."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.domain import Rates, digest, load_materials, read_json, validate_request
from src.evaluate import CASES, execution_metadata, inspect_case, trace_markdown


def check_evidence(root, mode):
    """Check the files and recorded observations underlying an acceptance index."""
    root = Path(root)
    folder = root / "examples" / mode
    problems = []
    try:
        summary = read_json(folder / "results.json")
        if not isinstance(summary, dict) or not isinstance(summary.get("cases"), list):
            raise ValueError("invalid summary structure")
        rows = summary["cases"]
        names = [row["case"] for row in rows]
        if any(not isinstance(name, str) for name in names):
            raise ValueError("invalid case name")
    except (OSError, ValueError, KeyError, TypeError):
        return [f"{mode} 验收汇总缺失或无法解析：examples/{mode}/results.json"]
    if summary.get("mode") != mode:
        problems.append(f"{mode} 汇总中的运行模式不一致")
    if set(names) != set(CASES) or len(names) != len(CASES):
        problems.append(f"{mode} 用例集合不完整或存在重复，应包含 {len(CASES)} 个指定用例")
    if summary.get("total") != len(rows) or summary.get("passed") != len(rows) or any(row.get("passed") is not True for row in rows):
        problems.append(f"{mode} 验收通过数量与用例记录不一致，或存在失败")
    try:
        if summary.get("materials_sha256") != digest(load_materials(root / "data/materials.json")):
            problems.append(f"{mode} 运行材料对应的素材与当前数据不一致")
        if summary.get("rates_sha256") != digest(Rates(root / "data/tool_rates.json").data):
            problems.append(f"{mode} 运行材料对应的费率与当前数据不一致")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        problems.append("当前素材或费率文件缺失或无法解析")

    real_paths = set()
    observed_change = False
    for row in rows:
        name = row["case"]
        if name not in CASES:
            continue
        label = f"{mode}/{name}"
        expected_refs = {"input": f"examples/inputs/{name}.json", "output": f"{name}.output.json", "trace": f"{name}.trace.md"}
        if any(row.get(key) != value for key, value in expected_refs.items()):
            problems.append(f"{label} 汇总引用的输入、输出或 Trace 路径不正确")
        paths = {"input": root / expected_refs["input"], "output": folder / expected_refs["output"], "trace": folder / expected_refs["trace"]}
        absent = [path.relative_to(root).as_posix() for path in paths.values() if not path.is_file()]
        if absent:
            problems.extend("缺少验收证据：" + path for path in absent)
            continue
        try:
            request = read_json(paths["input"])
            payload = read_json(paths["output"])
            if not isinstance(payload, dict) or payload.get("input") != request:
                raise ValueError("output input does not match")
            runs = payload["runs"]
            expected_runs = 2 if CASES[name].get("repeat") or CASES[name].get("resume") else 1
            if not isinstance(runs, list) or len(runs) != expected_runs or any(not isinstance(r, dict) for r in runs):
                raise ValueError("invalid run list")
            normalized, missing = validate_request(request)
            request_id = request.get("request_id") or "R-" + digest(normalized)[:20]
            for run in runs:
                if run.get("mode") != mode or run.get("request_id") != request_id:
                    raise ValueError("mode or request id mismatch")
                if not missing and run.get("request") != normalized:
                    raise ValueError("request mismatch")
                if mode == "real":
                    for step in run.get("steps", []):
                        if step.get("action") == "model_request":
                            continue
                        receipt = step.get("model_receipt") or {}
                        if receipt.get("source") != "real_model" or not receipt.get("response_id") or not receipt.get("tool_call_id"):
                            raise ValueError("missing real decision receipt")
                    for script in run.get("scripts", []):
                        receipt = script.get("generation_receipt") or {}
                        if receipt.get("source") != "real_model" or not receipt.get("response_id"):
                            raise ValueError("missing generation receipt")
            result = runs[-1]
            # Database equality is checked during evaluation while the DB exists.
            # Here we recheck the business assertions available in saved outputs.
            recomputed = inspect_case(name, runs)
            recorded = payload.get("checks")
            required_checks = set(recomputed) | {"database_matches_saved_result"}
            if (not isinstance(recorded, dict) or not required_checks.issubset(recorded)
                    or not all(value is True for value in recorded.values())
                    or not all(recomputed.values()) or row.get("checks") != recorded):
                problems.append(f"{label} 实际输出未通过当前断言，或与汇总检查结果不一致")
            metadata = execution_metadata(result)
            if any(row.get(key) != value for key, value in metadata.items()) or row.get("status") != result.get("status") or row.get("spent") != result.get("spent"):
                problems.append(f"{label} 汇总中的状态、消耗或动作路径与实际输出不一致")
            trace = paths["trace"].read_text(encoding="utf-8")
            if trace.strip() != trace_markdown(name, runs).strip():
                problems.append(f"{label} Trace 内容与实际输出不一致")
            if mode == "real" and metadata["real_model_responses"] >= 2:
                real_paths.add(tuple(metadata["actions"]))
                observed_change |= metadata["replanning_observed"] or metadata["failure_handling_observed"]
        except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
            problems.append(f"{label} 输入、实际输出或模型响应记录结构无效")
    if mode == "real" and (len(real_paths) < 2 or not observed_change):
        problems.append("实际运行文件中的真实模型动态路径证据不足")
    return problems


def main():
    missing = []
    required = ["README.md", "requirements.txt", ".env.example", "data/materials.json", "data/tool_rates.json",
                "src/main.py", "tests/test_agent.py", "tests/test_model.py", "tests/test_evaluation.py",
                "tests/test_submission.py", "examples/test-results.txt",
                "docs/01-requirements.md", "docs/02-solution.md", "docs/03-evaluation.md",
                "docs/04-ai-usage.md", "docs/05-retrospective.md", "examples/mock/results.json"]
    for name in required:
        if not (ROOT / name).is_file():
            missing.append("缺少文件：" + name)
    for mode in ("mock", "real"):
        missing.extend(check_evidence(ROOT, mode))
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    sha = git.stdout.strip() if git.returncode == 0 else None
    if not sha:
        missing.append("尚无本地提交 SHA")
    else:
        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
        if status.stdout.strip():
            missing.append("存在未提交的修改，当前 SHA 尚不代表完整交付")
        tracked_env = subprocess.run(["git", "ls-files", "--", ".env"], cwd=ROOT, capture_output=True, text=True)
        if tracked_env.stdout.strip():
            missing.append(".env 不应被 Git 跟踪")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"ready_for_submission": not missing, "commit_sha": sha, "remaining": missing,
                      "manual_confirmation": ["核对公司正式题号", "填写 GitHub URL 并确保评审可读", "阅读真实脚本并核对主题与素材"]}, ensure_ascii=False, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
