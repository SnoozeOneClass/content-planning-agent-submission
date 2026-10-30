"""Bounded model -> action -> observation loop, with authoritative tool state."""

from __future__ import annotations

import copy
import json
import re
import sqlite3
from datetime import datetime, timezone

from .domain import (BUSINESS_TOOLS, InputError, Rates, canonical, digest, new_state,
                     remaining, unique_ids, validate_request)
from .model import ModelError
from .storage import Store, execution_lock


def error_result(tool, code, message, *, status="rejected", retryable=False, data=None):
    return {"tool": tool, "status": status, "data": data,
            "error": {"code": code, "message": message, "retryable": retryable}, "charged": {"cost": 0, "duration": 0}}


class Agent:
    def __init__(self, model, store: Store, materials: dict, rates: Rates, *, max_steps=16, faults=None):
        if type(max_steps) is not int or max_steps < 1 or max_steps > 100:
            raise InputError("max_steps 必须在 1 到 100 之间")
        self.model, self.store, self.materials, self.rates = model, store, materials, rates
        self.max_steps = max_steps
        self.faults = faults or {}
        self._validate_faults()

    def _validate_faults(self):
        if not isinstance(self.faults, dict) or set(self.faults) - set(BUSINESS_TOOLS):
            raise InputError("故障配置必须以业务工具名为键")
        for spec in self.faults.values():
            if not isinstance(spec, dict) or set(spec) - {"at_calls", "always", "retryable", "message"}:
                raise InputError("故障配置字段无效")
            calls = spec.get("at_calls", [])
            if not isinstance(calls, list) or any(type(i) is not int or i < 1 for i in calls):
                raise InputError("at_calls 必须为正整数数组")
            if any(key in spec and type(spec[key]) is not bool for key in ("always", "retryable")):
                raise InputError("故障标记必须是布尔值")

    def run(self, raw, *, resume=False):
        request, missing = validate_request(raw)
        request_id = raw.get("request_id") or "R-" + digest(request)[:20]
        if missing:
            return {"request_id": request_id, "mode": self.model.mode, "status": "needs_input",
                    "missing_fields": missing, "reason": {"code": "MISSING_INPUT", "message": "请补充：" + "、".join(missing)},
                    "spent": {"cost": 0, "duration": 0}, "steps": [], "scripts": [], "saved_plan": None, "replayed": False}
        fingerprint = digest(request)
        config = digest({"materials": self.materials, "rates": self.rates.data, "mode": self.model.mode})
        with execution_lock(self.store.path):
            stored = self.store.get_run(request_id)
            if stored:
                old_fingerprint, state = stored
                if old_fingerprint != fingerprint or state["config_fingerprint"] != config:
                    return {"request_id": request_id, "mode": self.model.mode, "status": "incomplete",
                            "reason": {"code": "REQUEST_CONFLICT", "message": "同一 request_id 的输入、模式、素材或费用表已改变；请使用新 request_id"},
                            "saved_plan": None, "replayed": False}
                if state["status"] == "completed" or not resume:
                    return self.output(state, replayed=True)
                state["status"] = "running"
                state["reason"] = None
                state["last_result"] = {"status": "resuming", "message": "用户要求恢复任务；保留所有成功结果和累计费用/耗时"}
            else:
                state = new_state(request_id, request, self.model.mode, config)
                state["started_at"] = datetime.now(timezone.utc).isoformat()
            with self.store.transaction():
                self.store.checkpoint(state, fingerprint)
            while state["status"] == "running":
                if state["decisions"] >= self.max_steps:
                    state["status"] = "incomplete"
                    state["reason"] = {"code": "STEP_LIMIT", "message": f"达到 {self.max_steps} 次模型决策上限，任务未完成"}
                    break
                state["decisions"] += 1
                try:
                    decision = self.model.decide(copy.deepcopy(state), self.rates)
                except ModelError as exc:
                    state["status"] = "incomplete"
                    state["reason"] = {"code": "MODEL_ERROR", "message": str(exc)}
                    state["trace"].append({"step": state["decisions"], "source": self.model.mode,
                                           "action": "model_request", "result": {"status": "failed", "error": state["reason"]}})
                    break
                action = decision.get("action")
                args = decision.get("arguments")
                reason = decision.get("reason", "")
                receipt = decision.get("receipt", {})
                with self.store.transaction():
                    if action == "finish":
                        message = args.get("message", "模型选择停止") if isinstance(args, dict) else "模型选择停止"
                        state["status"] = "incomplete"
                        state["reason"] = {"code": "MODEL_STOPPED", "message": str(message)}
                        if state["plan"]:
                            final_quote = self.feasibility(state)
                            if not final_quote["feasible"]:
                                state["reason"]["shortfall"] = final_quote["shortfall"]
                        result = {"tool": "finish", "status": "stopped", "data": state["reason"], "charged": {"cost": 0, "duration": 0}}
                    else:
                        result = self.execute(state, action, args)
                    if state["trace"]:
                        state["trace"][-1]["next_action"] = action
                        state["trace"][-1]["next_reason"] = reason
                    state["trace"].append({"step": state["decisions"], "source": receipt.get("source", self.model.mode),
                        "action": action, "arguments": args, "reason": reason, "model_receipt": receipt,
                        "result": result, "observation_summary": self.summarize(result),
                        "spent_after": copy.deepcopy(state["spent"]), "remaining_after": remaining(state)})
                    state["last_result"] = result
                    if action == "save_plan" and result["status"] == "succeeded":
                        state["status"] = "completed"
                        state["reason"] = None
                    self.store.checkpoint(state, fingerprint)
            if state["trace"]:
                state["trace"][-1].setdefault("next_action", "end")
            with self.store.transaction():
                self.store.checkpoint(state, fingerprint)
            return self.output(state)

    def _plan(self, state, scripts):
        if not isinstance(scripts, list) or len(scripts) != state["request"]["script_count"]:
            raise InputError("候选计划必须包含用户要求的全部脚本")
        steps = []
        for p in scripts:
            if not isinstance(p, dict) or set(p) != {"step_id", "material_ids", "brief"}:
                raise InputError("每条脚本计划需要 step_id、material_ids、brief")
            if not isinstance(p["step_id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", p["step_id"]):
                raise InputError("step_id 只能包含字母、数字、下划线和短横线")
            if not isinstance(p["brief"], str) or not p["brief"].strip() or len(p["brief"]) > 2000:
                raise InputError("brief 必须是 1 到 2000 字符的字符串")
            ids = unique_ids(p["material_ids"])
            if any(i not in state["seen_materials"] or i not in self.materials for i in ids):
                raise InputError("必须使用本次任务已检索到的有效素材 ID")
            steps.append({"step_id": p["step_id"], "material_ids": ids, "brief": p["brief"].strip()})
        if len({p["step_id"] for p in steps}) != len(steps):
            raise InputError("step_id 不能重复")
        for step_id, script in state["scripts"].items():
            matching = [p for p in steps if p["step_id"] == step_id]
            if not matching or matching[0] != script["plan_step"]:
                raise InputError("重新规划必须原样保留已成功步骤")
        return steps

    def feasibility(self, state):
        pending = [p for p in state["plan"] if p["step_id"] not in state["scripts"]]
        costs = [self.rates.quote("generate_script", len(p["material_ids"])) for p in pending]
        save_cost, save_time = self.rates.quote("save_plan")
        future_cost = sum(c for c, _ in costs) + save_cost
        future_time = sum(t for _, t in costs) + save_time
        available = remaining(state)
        return {"feasible": future_cost <= available["budget"] and future_time <= available["time_budget"],
            "remaining_steps_cost": future_cost, "remaining_steps_duration": future_time,
            "projected_total_cost": state["spent"]["cost"] + future_cost,
            "projected_total_duration": state["spent"]["duration"] + future_time,
            "shortfall": {"budget": max(0, future_cost - available["budget"]), "time_budget": max(0, future_time - available["time_budget"])},
            "pending_step_ids": [p["step_id"] for p in pending], "includes_save": True}

    def execute(self, state, action, args):
        if action not in BUSINESS_TOOLS:
            return error_result(str(action), "UNKNOWN_TOOL", "未知工具")
        try:
            expected = {"search_materials": {"query"}, "estimate_plan": {"scripts"},
                        "generate_script": {"step_id"}, "save_plan": {"title", "summary"}}[action]
            if not isinstance(args, dict) or set(args) != expected:
                raise InputError("工具参数字段不符合定义")
            step, plan = None, None
            if action == "search_materials" and (not isinstance(args["query"], str) or not args["query"].strip() or len(args["query"]) > 200):
                raise InputError("query 必须是 1 到 200 字符的字符串")
            if action == "estimate_plan":
                plan = self._plan(state, args["scripts"])
            if action == "generate_script":
                if not isinstance(args["step_id"], str):
                    raise InputError("step_id 必须是字符串")
                if args["step_id"] in state["scripts"]:
                    return {"tool": action, "status": "cached", "data": state["scripts"][args["step_id"]], "charged": {"cost": 0, "duration": 0}}
                step = next((p for p in state["plan"] if p["step_id"] == args["step_id"]), None)
                if not step or not state.get("quote") or not state["quote"]["feasible"]:
                    return error_result(action, "DEPENDENCY_NOT_READY", "需要先获得可行的成本估算")
                live_quote = self.feasibility(state)
                if not live_quote["feasible"]:
                    return error_result(action, "CONSTRAINT_BLOCKED", "累计消耗变化后计划已不可行，请重新估算或停止", data=live_quote)
            if action == "save_plan":
                if any(not isinstance(args[k], str) or not args[k].strip() or len(args[k]) > 4000 for k in expected):
                    raise InputError("title 和 summary 必须是 1 到 4000 字符的字符串")
                if len(state["scripts"]) != state["request"]["script_count"] or not state["plan"] or any(p["step_id"] not in state["scripts"] for p in state["plan"]):
                    return error_result(action, "DEPENDENCY_NOT_READY", "所有要求的脚本必须实际生成成功后才能保存")
            cost, duration = self.rates.quote(action, len(step["material_ids"]) if step else 0)
            available = remaining(state)
            if cost > available["budget"] or duration > available["time_budget"]:
                return error_result(action, "CONSTRAINT_BLOCKED", "本次执行将超出预算或时间，未启动工具", data={"required": {"cost": cost, "duration": duration}, "remaining": available})
        except InputError as exc:
            return error_result(action, "INVALID_ARGUMENTS", str(exc))
        state["spent"]["cost"] += cost
        state["spent"]["duration"] += duration
        state["tool_calls"] += 1
        state["fault_counts"][action] = state["fault_counts"].get(action, 0) + 1
        charged = {"cost": cost, "duration": duration}
        spec = self.faults.get(action, {})
        if spec.get("always") or state["fault_counts"][action] in spec.get("at_calls", []):
            result = error_result(action, "INJECTED_TOOL_FAILURE", str(spec.get("message", "注入的工具执行失败")), status="failed", retryable=spec.get("retryable", True))
            result["charged"] = charged
            return result
        try:
            if action == "search_materials":
                data = self.search(args["query"])
                state["search_results"] = data
                state["seen_materials"] = list(dict.fromkeys(state["seen_materials"] + [m["material_id"] for m in data]))
            elif action == "estimate_plan":
                state["plan"] = plan
                data = self.feasibility(state)
                state["quote"] = data
                state["plan_revisions"].append({"decision_step": state["decisions"], "plan": copy.deepcopy(plan), "estimate": copy.deepcopy(data)})
            elif action == "generate_script":
                materials = [self.materials[i] for i in step["material_ids"]]
                script, receipt = self.model.write_script(state["request"]["topic"], step["brief"], materials)
                self.validate_script(script, step["material_ids"])
                data = {"step_id": step["step_id"], "plan_step": copy.deepcopy(step), "title": script["title"],
                        "scenes": script["scenes"], "material_ids": step["material_ids"], "generation_receipt": receipt}
                state["scripts"][step["step_id"]] = data
            else:
                body = {"title": args["title"], "summary": args["summary"], "topic": state["request"]["topic"],
                        "scripts": [state["scripts"][p["step_id"]] for p in state["plan"]],
                        "task_plan": copy.deepcopy(state["plan"]), "cost_total": state["spent"]["cost"],
                        "duration_total": state["spent"]["duration"], "mode": state["mode"]}
                data = self.store.save_plan(state["request_id"], body)
                state["saved_plan"] = data
            return {"tool": action, "status": "succeeded", "data": data, "error": None, "charged": charged}
        except (ModelError, InputError, sqlite3.Error) as exc:
            result = error_result(action, "TOOL_EXECUTION_FAILED", str(exc) if not isinstance(exc, sqlite3.Error) else "数据库写入失败", status="failed", retryable=True)
            result["charged"] = charged
            return result

    def search(self, query):
        query = re.sub(r"\s+", "", query.casefold())
        qgrams = set(query[i:i+2] for i in range(max(1, len(query)-1)))
        results = []
        for material in self.materials.values():
            content = (material["topic"] + material["content"]).casefold()
            grams = set(content[i:i+2] for i in range(max(1, len(content)-1)))
            overlap = len(qgrams & grams) / max(1, len(qgrams))
            topic_match = material["topic"].casefold() in query
            if overlap > 0 or topic_match:
                score = round(min(1.0, 0.7 * overlap + (0.3 if topic_match else 0)), 4)
                results.append({**material, "relevance_score": score})
        return sorted(results, key=lambda m: (-m["relevance_score"], m["material_id"]))[:8]

    @staticmethod
    def validate_script(script, ids):
        if not isinstance(script, dict) or not isinstance(script.get("title"), str) or not script["title"].strip():
            raise InputError("生成脚本缺少标题")
        scenes = script.get("scenes")
        if not isinstance(scenes, list) or not scenes or len(scenes) > 12:
            raise InputError("脚本需要 1 到 12 个分镜")
        for scene in scenes:
            if not isinstance(scene, dict) or any(not isinstance(scene.get(k), str) or not scene[k].strip() for k in ("visual", "narration")):
                raise InputError("分镜缺少画面或旁白")
            references = unique_ids(scene.get("material_ids"))
            if set(references) - set(ids):
                raise InputError("脚本引用了未提供的素材")

    @staticmethod
    def summarize(result):
        if result.get("error"):
            return result["error"]["code"] + ": " + result["error"]["message"]
        data, tool = result.get("data"), result.get("tool")
        if tool == "search_materials":
            return "检索返回 " + str(len(data)) + " 份素材：" + ",".join(m["material_id"] for m in data)
        if tool == "estimate_plan":
            return f"预计总费用 {data['projected_total_cost']}，总耗时 {data['projected_total_duration']}，可行={data['feasible']}"
        if tool == "generate_script":
            return "生成步骤 " + data["step_id"] + "，素材=" + ",".join(data["material_ids"])
        if tool == "save_plan":
            return "方案已保存：" + data["plan_id"]
        return str(data)

    @staticmethod
    def output(state, replayed=False):
        plan = []
        for p in state["plan"]:
            attempts = [t for t in state["trace"] if t.get("action") == "generate_script" and t.get("arguments", {}).get("step_id") == p["step_id"]]
            status = "succeeded" if p["step_id"] in state["scripts"] else ("failed" if any(t["result"]["status"] == "failed" for t in attempts) else "pending")
            plan.append({**p, "status": status, "depends_on": ["search_materials", "estimate_plan"], "attempts": len(attempts)})
        return {"request_id": state["request_id"], "request": state["request"], "mode": state["mode"],
                "status": state["status"], "reason": state["reason"], "spent": copy.deepcopy(state["spent"]),
                "remaining": remaining(state), "decision_steps": state["decisions"], "tool_calls": state["tool_calls"],
                "task_plan": plan, "plan_revisions": state["plan_revisions"], "scripts": list(state["scripts"].values()),
                "saved_plan": state["saved_plan"], "steps": state["trace"], "replayed": replayed,
                "evidence_scope": "真实模型调用与实际工具执行" if state["mode"] == "real" else "离线 Mock，仅验证流程，不证明真实模型决策效果"}
