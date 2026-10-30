"""Reproduce and save the executable test report and offline acceptance outputs."""

import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT,
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    header = f"Executed at: {datetime.now(timezone.utc).isoformat()}\nPython: {platform.python_version()}\nCommand: python -m unittest discover -s tests -v\nExit code: {result.returncode}\n\n"
    (ROOT / "examples/test-results.txt").write_text(header + result.stdout, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(result.stdout)
    if result.returncode:
        return result.returncode
    return subprocess.run([sys.executable, "-m", "src.evaluate", "--mode", "mock"], cwd=ROOT, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
