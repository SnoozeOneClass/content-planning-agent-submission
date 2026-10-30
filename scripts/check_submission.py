"""Read-only readiness check. Offline success alone never counts as real evidence."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    missing = []
    required = ["README.md", "requirements.txt", ".env.example", "data/materials.json", "data/tool_rates.json",
                "src/main.py", "tests/test_agent.py", "tests/test_model.py", "examples/test-results.txt",
                "docs/01-requirements.md", "docs/02-solution.md", "docs/03-evaluation.md",
                "docs/04-ai-usage.md", "docs/05-retrospective.md", "examples/mock/results.json"]
    for name in required:
        if not (ROOT / name).is_file():
            missing.append("缺少文件：" + name)
    for mode in ("mock", "real"):
        path = ROOT / "examples" / mode / "results.json"
        if not path.exists():
            missing.append("缺少 " + mode + " 验收运行结果")
            continue
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary["passed"] != summary["total"]:
            missing.append(mode + " 验收存在失败")
        if summary["total"] < 12:
            missing.append(mode + " 尚未覆盖全部预设验收用例")
        if mode == "real":
            paths = {tuple(c["actions"]) for c in summary["cases"] if c.get("real_model_responses", 0) >= 2}
            changed = any(c.get("replanning_observed") or c.get("failure_handling_observed") for c in summary["cases"])
            if len(paths) < 2 or not changed:
                missing.append("真实模型至少两条不同动态执行路径的证据不足")
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
