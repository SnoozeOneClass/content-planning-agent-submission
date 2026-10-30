"""Real native tool calling and an explicitly separate deterministic offline mock."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .domain import canonical, remaining
from .prompts import SYSTEM_PROMPT, TOOLS, WRITER_PROMPT


class ModelError(RuntimeError):
    pass


def reject_nonfinite(value):
    raise ValueError("模型 JSON 不能包含非有限数值")


def load_env(path: str | Path):
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().startswith("MODEL_"):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelError("模型接口发生重定向，请直接配置最终 MODEL_BASE_URL")


class ChatModel:
    mode = "real"

    def __init__(self, base_url=None, api_key=None, model=None, timeout=None):
        self.base_url = (base_url or os.getenv("MODEL_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("MODEL_API_KEY", "")
        self.name = model or os.getenv("MODEL_NAME", "deepseek-flash")
        self.timeout = float(timeout or os.getenv("MODEL_TIMEOUT_SECONDS", "90"))
        self.opener = urllib.request.build_opener(NoRedirect())

    def _post(self, messages, *, tools=None, json_output=False):
        if not self.api_key:
            raise ModelError("MODEL_API_KEY 未配置；可配置 .env 后使用 --resume，或独立运行 --mode mock")
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
            raise ModelError("MODEL_BASE_URL 必须使用 HTTPS（本机测试服务除外）")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ModelError("MODEL_BASE_URL 不得包含凭据、查询参数或片段")
        payload = {"model": self.name, "messages": messages, "stream": False, "max_tokens": 3500, "temperature": 0}
        if parsed.hostname == "api.deepseek.com":
            payload["thinking"] = {"type": "disabled"}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "required"
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(self.base_url + "/chat/completions", data=canonical(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"), parse_constant=reject_nonfinite)
            message = result["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("message must be an object")
            return message, {"response_id": result.get("id"), "model": result.get("model", self.name), "source": "real_model"}
        except urllib.error.HTTPError as exc:
            # Do not copy service bodies or authentication headers into traces.
            raise ModelError(f"模型接口返回 HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelError("模型接口网络连接失败或超时") from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError("模型接口返回的响应结构无效") from None

    def decide(self, state, rates):
        context = {k: state[k] for k in ("request", "spent", "search_results", "plan", "scripts", "quote", "last_result", "reason")}
        context["remaining"] = remaining(state)
        context["tool_rates"] = rates.data
        context["history"] = [{"action": t.get("action"), "arguments": t.get("arguments"), "result": t.get("result")} for t in state["trace"][-12:]]
        context["steps_used"] = state["decisions"]
        # Each request contains the current observations and prior tool results.
        # The next action is chosen by the model, never a Python routing policy.
        message, receipt = self._post([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "根据以下实际任务状态选择一个下一步动作：\n" + canonical(context)},
        ], tools=TOOLS)
        calls = message.get("tool_calls") or []
        if len(calls) != 1:
            raise ModelError("模型必须每轮返回且仅返回一个工具调用")
        try:
            call = calls[0]
            arguments = json.loads(call["function"]["arguments"], parse_constant=reject_nonfinite)
            if not isinstance(arguments, dict):
                raise ValueError()
            reason = arguments.pop("reason", "")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError()
            return {"action": call["function"]["name"], "arguments": arguments, "reason": reason[:600],
                    "receipt": {**receipt, "tool_call_id": call.get("id")}}
        except (KeyError, TypeError, ValueError):
            raise ModelError("模型工具调用参数或公开动作依据无效") from None

    def write_script(self, topic, brief, materials):
        message, receipt = self._post([
            {"role": "system", "content": WRITER_PROMPT},
            {"role": "user", "content": canonical({"topic": topic, "brief": brief, "materials": materials})},
        ], json_output=True)
        try:
            content = message.get("content") or ""
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
            return json.loads(content, parse_constant=reject_nonfinite), receipt
        except (ValueError, TypeError):
            raise ModelError("脚本生成未返回合法 JSON") from None


class MockModel:
    """Offline flow verification only: this is NOT evidence of model reasoning."""
    mode = "mock"
    name = "deterministic-offline-mock"

    def decision(self, action, arguments, reason):
        return {"action": action, "arguments": arguments, "reason": reason,
                "receipt": {"source": "offline_mock", "model": self.name}}

    def decide(self, state, rates):
        last = state.get("last_result") or {}
        error = last.get("error") or {}
        if last.get("status") == "failed" and not error.get("retryable", False):
            return self.decision("finish", {"message": error.get("message", "工具失败")}, "Mock：不可恢复错误，保留成功结果并停止。")
        if not state["search_results"]:
            searches = sum(t.get("action") == "search_materials" for t in state["trace"])
            if searches >= 2:
                return self.decision("finish", {"message": "未检索到支持主题的资料，请补充素材"}, "Mock：两次检索无结果。")
            return self.decision("search_materials", {"query": state["request"]["topic"]}, "Mock：先获取可用参考资料。")
        if last.get("status") == "failed" and last.get("tool") == "save_plan":
            return self.decision("save_plan", {"title": state["request"]["topic"] + "内容活动方案", "summary": "复用成功脚本，重试保存。"}, "Mock：保存临时失败，保留脚本。")
        if not state["plan"]:
            ids = [m["material_id"] for m in state["search_results"][:4]]
            scripts = [{"step_id": f"script_{i+1}", "material_ids": ids, "brief": state["request"]["topic"] + f"介绍第{i+1}条"} for i in range(state["request"]["script_count"])]
            return self.decision("estimate_plan", {"scripts": scripts}, "Mock：先估算候选计划。")
        if last.get("tool") == "estimate_plan" and last.get("status") == "succeeded" and not last["data"]["feasible"]:
            pending = [p for p in state["plan"] if p["step_id"] not in state["scripts"]]
            options = [p for p in pending if len(p["material_ids"]) > 1]
            if not options:
                return self.decision("finish", {"message": "最小可执行计划仍不满足预算或时间，缺口见估算结果"}, "Mock：无可行方案。")
            scripts = json.loads(json.dumps(state["plan"]))
            for p in scripts:
                if p["step_id"] not in state["scripts"]:
                    p["material_ids"] = p["material_ids"][:max(1, len(p["material_ids"]) // 2)]
            return self.decision("estimate_plan", {"scripts": scripts}, "Mock：根据超限估算减少选用素材，再次估算。")
        if last.get("status") in {"failed", "rejected"} or last.get("status") == "resuming":
            return self.decision("estimate_plan", {"scripts": state["plan"]}, "Mock：根据实际消耗重新估算未完成步骤。")
        for p in state["plan"]:
            if p["step_id"] not in state["scripts"]:
                return self.decision("generate_script", {"step_id": p["step_id"]}, "Mock：执行估算通过的未完成步骤。")
        return self.decision("save_plan", {"title": state["request"]["topic"] + "内容活动方案", "summary": "围绕主题组织已生成脚本，按脚本顺序完成内容准备。"}, "Mock：所有脚本成功后保存。")

    def write_script(self, topic, brief, materials):
        return {"title": brief, "scenes": [{"visual": "展示资料所述功能的使用画面", "narration": m["content"], "material_ids": [m["material_id"]]} for m in materials]}, {"source": "offline_mock", "model": self.name}
