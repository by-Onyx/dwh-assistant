import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from assistant import Agent, Client, ProtocolError, parse_response
from dwh_tools import dispatch

class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
    def complete(self, messages, emit=None):
        return next(self.responses)

class Tests(unittest.TestCase):
    def test_call_and_answer(self):
        self.assertEqual(parse_response('<call>{"name":"catalog","arguments":{"table":"orders"}}</call>')[0], "call")
        self.assertEqual(parse_response("<answer>ok</answer>"), ("answer", "ok"))
    def test_reject_untrusted_protocol(self):
        for text in ['x<answer>ok</answer>', '<call>{"name":"x","name":"y","arguments":{}}</call>', '<call>[]</call>', '<answer></answer>', '<answer><call>{}</call></answer>', '<call>{"name":"x","arguments":{}} garbage</call>']:
            with self.subTest(text=text), self.assertRaises(ProtocolError):
                parse_response(text)
    def test_dispatch_allowlist(self):
        for name, args in [("__import__", {}), ("catalog", {"table": "orders", "extra": 1}), ("catalog", {"table": []}), ("check_design", {"design": {}})]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                dispatch(name, args)
    def test_check_design(self):
        self.assertFalse(dispatch("check_design", {"design": {"grain": "", "facts": [], "dimensions": ["customer"]}})["valid"])
        result = dispatch("check_design", {"design": {"grain": "position", "facts": ["quantity"], "dimensions": ["product"]}})
        self.assertTrue(result["valid"])
        self.assertIn("структура", result["scope"])
    def test_catalog_copy_and_missing(self):
        result = dispatch("catalog", {"table": "orders"})
        result["fields"].append("injected")
        self.assertNotIn("injected", dispatch("catalog", {"table": "orders"})["fields"])
        self.assertIn("error", dispatch("catalog", {"table": "payments"}))
    def test_agent_executes_and_retains_history(self):
        agent = Agent(FakeClient(['<call>{"name":"catalog","arguments":{"table":"orders"}}</call>', '<answer>order_id</answer>', '<answer>next</answer>']))
        self.assertEqual(len(agent.ask("fields")["calls"]), 1)
        self.assertIn("observation", agent.messages[-2]["content"])
        agent.ask("follow up")
        self.assertTrue(any(m["content"] == "fields" for m in agent.messages))
        agent.reset()
        self.assertEqual(len(agent.messages), agent.initial_length)
    def test_answer_phase_isolated_from_examples(self):
        class Spy(FakeClient):
            def complete(self, messages, emit=None):
                self.last_messages = messages
                return super().complete(messages, emit)
        client = Spy(['<call>{"name":"catalog","arguments":{"table":"orders"}}</call>', 'Поля: order_id.'])
        result = Agent(client).ask("fields")
        self.assertEqual(result["answer"], "Поля: order_id.")
        self.assertEqual(len(client.last_messages), 2)
        self.assertIn("observation", client.last_messages[1]["content"])
    def test_repair_and_loop_limit(self):
        agent = Agent(FakeClient(["bad", "<answer>ok</answer>"]))
        self.assertEqual(agent.ask("test")["repairs"], 1)
        agent = Agent(FakeClient(["bad"] * 3))
        with self.assertRaises(RuntimeError):
            agent.ask("test")
        self.assertEqual(len(agent.messages), agent.initial_length)
    def test_repeated_tool_not_executed(self):
        call = '<call>{"name":"catalog","arguments":{"table":"orders"}}</call>'
        agent = Agent(FakeClient([call, call, "<answer>ok</answer>"]))
        result = agent.ask("test")
        self.assertEqual(len(result["calls"]), 1)
        self.assertEqual(result["repairs"], 1)
    def test_sse_uses_content_and_no_native_tools(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def __iter__(self):
                return iter([b": heartbeat\n", b'data: {"choices":[{"delta":{"content":"<answer>ok</answer>"},"finish_reason":null}]}\n', b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n', b"data: [DONE]\n"])
        with patch("assistant.request.urlopen", return_value=Response()) as send:
            self.assertEqual(Client("local-3b").complete([]), "<answer>ok</answer>")
            payload = json.loads(send.call_args.args[0].data)
            self.assertNotIn("tools", payload)
            self.assertTrue(payload["stream"])

if __name__ == "__main__":
    unittest.main()
