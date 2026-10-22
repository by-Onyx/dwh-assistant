import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from langchain_core.runnables import RunnableLambda, RunnableSequence
from dwh_agent.fact_memory import FileFactMemory, MemoryFormatError, validate_patch
from dwh_agent.fact_agent import FactAgent


def update(key, value, evidence=None):
    return {"updates": [{"key": key, "value": value, "evidence": evidence or value}]}


class FactMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "memory.json"

    def test_facts_survive_recreation_without_messages(self):
        first = FileFactMemory(self.path, "alice")
        first.save_context({"message": "Меня зовут Анна"}, {"fact_patch": update("name", "Анна")})
        second = FileFactMemory(self.path, "alice")
        self.assertEqual(second.load_memory_variables(), {"facts": {"name": "Анна"}})
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document, {"version": 1, "profiles": {"alice": {"facts": {"name": "Анна"}}}})
        self.assertNotIn("Меня зовут", self.path.read_text(encoding="utf-8"))
        self.assertEqual(second.next_question(), "С каким стеком данных вы работаете?")

    def test_profile_isolation_and_clear(self):
        a, b = FileFactMemory(self.path, "a"), FileFactMemory(self.path, "b")
        a.save_context({"message": "Анна"}, {"fact_patch": update("name", "Анна")})
        b.save_context({"message": "Борис"}, {"fact_patch": update("name", "Борис")})
        a.forget()
        self.assertEqual(a.load_memory_variables()["facts"], {})
        self.assertEqual(b.load_memory_variables()["facts"], {"name": "Борис"})

    def test_correction_replaces_only_one_field(self):
        memory = FileFactMemory(self.path)
        memory.save_context({"message": "Анна SQL"}, {"fact_patch": {"updates": [
            update("name", "Анна")["updates"][0], update("stack", "SQL")["updates"][0]]}})
        memory.save_context({"message": "Теперь мой стек Python"}, {"fact_patch": update("stack", "Python")})
        self.assertEqual(memory.load_memory_variables()["facts"], {"name": "Анна", "stack": "Python"})
        memory.forget("stack")
        self.assertEqual(memory.next_question(), "С каким стеком данных вы работаете?")

    def test_invalid_extraction_cannot_change_memory(self):
        memory = FileFactMemory(self.path)
        memory.save_context({"message": "Анна"}, {"fact_patch": update("name", "Анна")})
        before = self.path.read_bytes()
        invalid = [update("name", "Борис"), update("password", "секрет"),
                   update("name", "Борис", "Анна"), {"updates": [update("name", "Анна")["updates"][0]] * 2}]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                memory.save_context({"message": "Анна"}, {"fact_patch": candidate})
            self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_profile_ids(self):
        for user_id in ["../other", "", "a/b", "x" * 65]:
            with self.subTest(user_id=user_id), self.assertRaises(ValueError):
                FileFactMemory(self.path, user_id)

    def test_corrupt_file_is_not_reset(self):
        for content in ['{bad', '{"version":1,"version":2,"profiles":{}}',
                        '{"version":1,"profiles":{"default":{"messages":[]}}}']:
            self.path.write_text(content, encoding="utf-8")
            with self.assertRaises(MemoryFormatError):
                FileFactMemory(self.path)
            self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_failed_atomic_replace_preserves_file(self):
        memory = FileFactMemory(self.path)
        memory.save_context({"message": "Анна"}, {"fact_patch": update("name", "Анна")})
        before = self.path.read_bytes()
        with patch("dwh_agent.fact_memory.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                memory.save_context({"message": "Борис"}, {"fact_patch": update("name", "Борис")})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_concurrent_profile_writes_do_not_lose_updates(self):
        def save(index):
            memory = FileFactMemory(self.path, f"user_{index}")
            memory.save_context({"message": f"Name{index}"}, {"fact_patch": update("name", f"Name{index}")})
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(save, range(8)))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["profiles"]), 8)

    def test_langchain_chain_and_saved_facts_reach_answer(self):
        prompts, events = [], []
        extractor = RunnableLambda(lambda prompt: json.dumps(update("name", "Анна"), ensure_ascii=False))
        def respond(prompt):
            prompts.append(prompt.to_messages())
            return "Анна, какой у вас стек?"
        agent = FactAgent(FileFactMemory(self.path), extractor=extractor,
                          responder=RunnableLambda(respond), on_event=events.append)
        self.assertIsInstance(agent.extract_chain, RunnableSequence)
        self.assertIsInstance(agent.answer_chain, RunnableSequence)
        result = agent.ask("Меня зовут Анна")
        self.assertTrue(result["extraction_ok"])
        self.assertIn('"name": "Анна"', prompts[0][-1].content)
        self.assertNotIn('"role"', self.path.read_text(encoding="utf-8"))
        self.assertEqual([e["event"] for e in events], ["memory_loaded", "memory_saved", "answer_ready"])
        self.assertNotIn("memory_saved", result["answer"])

    def test_bad_json_retries_and_keeps_old_memory(self):
        memory = FileFactMemory(self.path)
        memory.save_context({"message": "Анна"}, {"fact_patch": update("name", "Анна")})
        calls = []
        def broken(prompt):
            calls.append(prompt)
            return '{"updates":[],"updates":[]}'
        agent = FactAgent(memory, extractor=RunnableLambda(broken), responder=RunnableLambda(lambda _: "Анна"))
        result = agent.ask("Как меня зовут?")
        self.assertFalse(result["extraction_ok"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["facts"], {"name": "Анна"})

    def test_extractor_never_receives_old_profile_values(self):
        memory = FileFactMemory(self.path)
        memory.save_context({"message": "Анна"}, {"fact_patch": update("name", "Анна")})
        seen = []
        def extract(prompt):
            seen.append("\n".join(message.content for message in prompt.to_messages()))
            return '{"updates": []}'
        agent = FactAgent(memory, extractor=RunnableLambda(extract),
                          responder=RunnableLambda(lambda _: "Вас зовут Анна"))
        self.assertEqual(agent.ask("Как меня зовут?")["facts"], {"name": "Анна"})
        self.assertNotIn("Анна", seen[0])

    def test_failed_answer_does_not_erase_saved_facts(self):
        def fail(_):
            raise RuntimeError("LLM unavailable")
        agent = FactAgent(FileFactMemory(self.path),
                          extractor=RunnableLambda(lambda _: json.dumps(update("name", "Анна"))),
                          responder=RunnableLambda(fail))
        with self.assertRaises(RuntimeError):
            agent.ask("Анна")
        self.assertEqual(FileFactMemory(self.path).load_memory_variables()["facts"], {"name": "Анна"})

    def test_questions_do_not_create_history_or_change_facts(self):
        memory = FileFactMemory(self.path)
        agent = FactAgent(memory, extractor=RunnableLambda(lambda _: '{"updates":[]}'),
                          responder=RunnableLambda(lambda _: "Как к вам обращаться?"))
        result = agent.ask("Продолжим знакомство")
        self.assertEqual(result["facts"], {})
        self.assertFalse(self.path.exists())

    def test_ui_routes_diagnostics_to_separate_cell(self):
        from dwh_agent.notebook_ui import NotebookChat
        ui = NotebookChat()
        agent = FactAgent(FileFactMemory(self.path),
                          extractor=RunnableLambda(lambda _: json.dumps(update("name", "Анна"))),
                          responder=RunnableLambda(lambda _: "Анна, какой у вас стек?"), on_event=ui.service)
        ui.attach(agent)
        ui.input.value = "Меня зовут Анна"
        ui._submit(None)
        chat = "".join(item.get("text", "") for item in ui.chat_output.outputs)
        service = "".join(item.get("text", "") for item in ui.service_output.outputs)
        self.assertIn("Ассистент: Анна", chat)
        self.assertNotIn("memory_saved", chat)
        self.assertIn("memory_saved", service)
        self.assertIsNot(ui.chat_output, ui.service_output)

if __name__ == "__main__":
    unittest.main()
