"""CLI entry point. Business incomplete statuses are JSON, invocation errors exit 2."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .agent import Agent
from .domain import ROOT, InputError, Rates, load_materials, read_json
from .model import ChatModel, MockModel, load_env
from .storage import BusyError, Store


def main(argv=None):
    parser = argparse.ArgumentParser(description="内容任务规划 Agent")
    parser.add_argument("--input", required=True, help="用户请求 JSON 文件")
    parser.add_argument("--mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--db", default=str(ROOT / "runtime/agent.sqlite3"))
    parser.add_argument("--materials", default=str(ROOT / "data/materials.json"))
    parser.add_argument("--rates", default=str(ROOT / "data/tool_rates.json"))
    parser.add_argument("--faults", help="独立故障配置，不属于用户业务输入")
    parser.add_argument("--resume", action="store_true", help="在持久化成功结果和累计消耗基础上继续")
    parser.add_argument("--max-steps", type=int, default=16)
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--output", help="将完整实际结果与 Trace 写入 JSON 文件")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    store = None
    try:
        load_env(args.env_file)
        materials, rates = load_materials(args.materials), Rates(args.rates)
        model = MockModel() if args.mode == "mock" else ChatModel()
        store = Store(args.db)
        result = Agent(model, store, materials, rates, max_steps=args.max_steps,
                       faults=read_json(args.faults) if args.faults else None).run(read_json(args.input), resume=args.resume)
        code = 0
    except (InputError, OSError, ValueError, sqlite3.Error, BusyError) as exc:
        result = {"status": "incomplete", "reason": {"code": "INVOCATION_ERROR", "message": str(exc)}, "saved_plan": None}
        code = 2
    finally:
        if store:
            store.close()
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
