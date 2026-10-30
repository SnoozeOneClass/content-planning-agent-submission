"""HTTP serialization checks use an in-process transport stub, not model evidence."""

import json
import io
import urllib.error
import unittest

from src.domain import Rates, new_state
from src.model import ChatModel, ModelError


class TransportStub:
    def __init__(self):
        self.requests, self.responses = [], []

    def open(self, request, timeout):
        self.requests.append(json.loads(request.data))
        status, response = self.responses.pop(0)
        body = io.BytesIO(json.dumps(response).encode())
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "test HTTP error", {}, body)
        return body


class ModelProtocolTests(unittest.TestCase):
    def setUp(self):
        self.server = TransportStub()
        self.model = ChatModel(base_url="https://api.deepseek.com", api_key="test-only-not-a-secret", model="protocol-test")
        self.model.opener = self.server

    def response(self, message):
        self.server.responses.append((200, {"id": "test-response", "model": "protocol-test", "choices": [{"message": message}]}))

    def test_native_tool_call_is_parsed_and_observation_is_in_context(self):
        self.response({"tool_calls": [{"id": "call-test", "function": {"name": "search_materials", "arguments": json.dumps({"query": "字幕", "reason": "查询参考资料"})}}]})
        state = new_state("test", {"topic": "字幕", "budget": 10, "time_budget": 30, "script_count": 1}, "real", "test")
        state["last_result"] = {"status": "succeeded", "data": {"feasible": False}}
        decision = self.model.decide(state, Rates())
        self.assertEqual(decision["action"], "search_materials")
        self.assertEqual(decision["arguments"], {"query": "字幕"})
        self.assertEqual(decision["receipt"]["tool_call_id"], "call-test")
        payload = self.server.requests[0]
        context = json.loads(payload["messages"][-1]["content"].split("\n", 1)[1])
        self.assertFalse(context["last_result"]["data"]["feasible"])
        self.assertEqual(len(payload["tools"]), 5)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["tool_choice"], "required")

    def test_writer_uses_separate_json_generation(self):
        self.response({"content": json.dumps({"title": "标题", "scenes": [{"visual": "画面", "narration": "旁白", "material_ids": ["M01"]}]})})
        script, receipt = self.model.write_script("字幕", "介绍字幕", [{"material_id": "M01", "content": "添加字幕"}])
        self.assertEqual(script["title"], "标题")
        self.assertEqual(self.server.requests[0]["response_format"], {"type": "json_object"})
        self.assertNotIn("tools", self.server.requests[0])

    def test_http_error_does_not_echo_service_body_or_secret(self):
        self.server.responses.append((401, {"error": "test-only-not-a-secret"}))
        with self.assertRaises(ModelError) as error:
            self.model._post([])
        self.assertEqual(str(error.exception), "模型接口返回 HTTP 401")

    def test_malformed_tool_json_fails_clearly(self):
        self.response({"tool_calls": [{"function": {"name": "search_materials", "arguments": "bad"}}]})
        state = new_state("test", {"topic": "字幕", "budget": 10, "time_budget": 30}, "real", "test")
        with self.assertRaises(ModelError):
            self.model.decide(state, Rates())

    def test_no_silent_mock_when_key_is_missing(self):
        model = ChatModel(api_key="")
        with self.assertRaises(ModelError):
            model._post([])

    def test_insecure_remote_url_is_rejected(self):
        model = ChatModel(base_url="http://example.com", api_key="test-only-not-a-secret")
        with self.assertRaises(ModelError):
            model._post([])


if __name__ == "__main__":
    unittest.main()
