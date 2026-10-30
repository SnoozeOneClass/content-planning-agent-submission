"""Small, deterministic business rules shared by estimates and execution."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BUSINESS_TOOLS = ("search_materials", "estimate_plan", "generate_script", "save_plan")


class InputError(ValueError):
    pass


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def validate_request(raw: Any) -> tuple[dict, list[str]]:
    if not isinstance(raw, dict):
        raise InputError("输入必须是 JSON 对象")
    allowed = {"request_id", "topic", "budget", "time_budget", "script_count"}
    unknown = set(raw) - allowed
    if unknown:
        raise InputError("未知输入字段：" + ", ".join(sorted(unknown)))
    missing = [key for key in ("topic", "budget", "time_budget") if key not in raw or raw[key] is None or raw[key] == ""]
    if "topic" not in missing and (not isinstance(raw["topic"], str) or not raw["topic"].strip()):
        raise InputError("topic 必须是非空字符串")
    for key in ("budget", "time_budget"):
        if key not in missing and not valid_number(raw[key]):
            raise InputError(f"{key} 必须是非负有限数值")
    count = raw.get("script_count", 1)
    if type(count) is not int or not 1 <= count <= 5:
        raise InputError("script_count 必须是 1 到 5 的整数")
    if "request_id" in raw and (not isinstance(raw["request_id"], str) or not raw["request_id"].strip() or len(raw["request_id"]) > 100):
        raise InputError("request_id 必须为不超过 100 字符的非空字符串")
    request = {k: v for k, v in raw.items() if k != "request_id"}
    if isinstance(request.get("topic"), str):
        request["topic"] = request["topic"].strip()
    request["script_count"] = count
    return request, missing


def load_materials(path: str | Path) -> dict[str, dict]:
    rows = read_json(path)
    if not isinstance(rows, list) or not rows:
        raise InputError("素材文件必须是非空数组")
    materials = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"material_id", "topic", "content"}:
            raise InputError("每份素材仅包含 material_id、topic、content")
        if any(not isinstance(value, str) or not value.strip() for value in row.values()):
            raise InputError("素材字段必须为非空字符串")
        if row["material_id"] in materials:
            raise InputError("素材 ID 重复")
        materials[row["material_id"]] = row
    return materials


def unique_ids(ids: Any) -> list[str]:
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids):
        raise InputError("material_ids 必须是非空字符串数组")
    return list(dict.fromkeys(ids))


class Rates:
    def __init__(self, path: str | Path = ROOT / "data/tool_rates.json"):
        self.data = read_json(path)
        expected = {
            "search_materials": {"cost", "duration"},
            "estimate_plan": {"cost", "duration"},
            "generate_script": {"base_cost", "cost_per_material", "base_duration", "duration_per_material"},
            "save_plan": {"cost", "duration"},
        }
        for name, keys in expected.items():
            if not isinstance(self.data.get(name), dict) or set(self.data[name]) != keys or any(not valid_number(v) for v in self.data[name].values()):
                raise InputError(f"费用表 {name} 无效")

    def quote(self, name: str, n: int = 0) -> tuple[float, float]:
        rate = self.data[name]
        if name == "generate_script":
            if n < 1:
                raise InputError("生成至少需要一份素材")
            return rate["base_cost"] + rate["cost_per_material"] * n, rate["base_duration"] + rate["duration_per_material"] * n
        return rate["cost"], rate["duration"]


def new_state(request_id: str, request: dict, mode: str, config_fingerprint: str) -> dict:
    return {
        "request_id": request_id, "request": request, "mode": mode,
        "config_fingerprint": config_fingerprint, "status": "running", "reason": None,
        "spent": {"cost": 0, "duration": 0}, "decisions": 0, "tool_calls": 0,
        "search_results": [], "seen_materials": [], "plan": [], "plan_revisions": [],
        "scripts": {}, "trace": [], "quote": None, "last_result": None,
        "saved_plan": None, "fault_counts": {}, "model_receipts": [],
    }


def remaining(state: dict) -> dict:
    return {"budget": state["request"]["budget"] - state["spent"]["cost"],
            "time_budget": state["request"]["time_budget"] - state["spent"]["duration"]}
