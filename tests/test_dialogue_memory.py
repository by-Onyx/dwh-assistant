from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from langchain_core.runnables import RunnableLambda

from dwh_agent.dialogue_memory import DialogueMemory
from dwh_agent.fact_agent import FactAgent
from dwh_agent.fact_memory import FileFactMemory
from dwh_agent.notebook_ui import NotebookChat


class DialogueTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.memory = FileFactMemory(Path(temp.name) / "facts.json")
        self.answers, self.extractions, self.summaries, self.events = [], [], [], []

        def recording(target, result):
            def invoke(prompt):
                target.append([msg.content for msg in prompt.to_messages()])
                return result
            return RunnableLambda(invoke)

        self.agent = FactAgent(
            self.memory, window_turns=1, on_event=self.events.append,
            extractor=recording(self.extractions, '{"updates":[]}'),
            responder=recording(self.answers, "Ответ"), summarizer=recording(self.summaries, "Сводка 1"),
        )

    def test_window_eviction_and_incremental_summary(self):
        for question in ("Запрос А", "Запрос Б", "Запрос В"):
            self.agent.ask(question)
        self.assertIn("Запрос А", self.answers[1])
        self.assertNotIn("Запрос А", self.answers[2])
        self.assertIn("Запрос Б", self.answers[2])
        self.assertIn("Ответ", self.answers[2])
        self.assertIn("Сводка 1", "\n".join(self.answers[2]))
        self.assertIn("Запрос А", self.summaries[0])
        self.assertIn("Запрос Б", self.summaries[1])
        self.assertIn("Сводка 1", "\n".join(self.summaries[1]))
        self.assertNotIn("Запрос А", "\n".join(self.extractions[-1]))
        self.assertNotIn("Сводка 1", "\n".join(self.extractions[-1]))
        self.assertFalse(self.memory.path.exists())

    def test_command_persists_and_changes_actual_answer_instruction(self):
        self.agent.ask("Что такое grain?")
        self.assertEqual(self.events[-1]["teaching_mode"], "general")
        for level, mode, instruction in [
            ("начинающий аналитик", "beginner", "один простой пример"),
            ("средний уровень", "intermediate", "прикладной пример"),
            ("эксперт", "advanced", "ограничения и компромиссы"),
        ]:
            with self.subTest(level=level):
                self.agent.ask("/remember level " + level)
                self.assertEqual(FileFactMemory(self.memory.path).load_memory_variables()["facts"]["level"], level)
                self.agent.ask("Что такое grain?")
                self.assertEqual(self.events[-1]["teaching_mode"], mode)
                self.assertIn(instruction, self.answers[-1][0])
        self.assertEqual(len(self.extractions), 4)
        self.assertEqual(len(self.answers), 4)

    def test_practice_in_chat_uses_persisted_level_and_enters_history(self):
        self.agent.ask("/remember level эксперт")
        ui = NotebookChat()
        events = []
        reopened = FactAgent(FileFactMemory(self.memory.path), on_event=events.append)
        ui.attach(reopened)
        ui.input.value = "/practice"
        ui._submit(None)
        output = "".join(item["text"] for item in ui.chat_output.outputs)
        self.assertEqual(events[-1]["teaching_mode"], "advanced")
        self.assertIn("Возврат", output)
        self.assertIn("Возврат", reopened.dialogue.messages()[-1].content)
        self.agent.ask("/remember level новичок")
        self.assertIn("три товарные позиции", self.agent.ask("/practice")["answer"])

    def test_invalid_command_preserves_profile_and_skips_models(self):
        self.agent.ask("/remember goals Построить витрину продаж")
        before = self.memory.path.read_bytes()
        for command in ("/remember", "/remember goals", "/remember unknown A", "/remember level " + "x"*501):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.agent.ask(command)
            self.assertEqual(before, self.memory.path.read_bytes())
        self.assertFalse(self.extractions or self.answers or self.summaries)

    def test_failed_summarization_leaves_previous_window_intact(self):
        self.agent.ask("Первый")
        self.agent.summary_chain = RunnableLambda(lambda _: "   ")
        with self.assertRaisesRegex(ValueError, "пустую сводку"):
            self.agent.ask("Второй")
        self.assertEqual([m.content for m in self.agent.dialogue.messages()], ["Первый", "Ответ"])
        self.assertEqual(self.agent.dialogue.summary, "")

    def test_ui_forget_and_clear_drop_related_dialogue(self):
        ui = NotebookChat()
        ui.attach(self.agent)
        for command in ("/forget level", "/clear"):
            for message in ("/remember level новичок", "Первая тема", "Вторая тема"):
                ui.input.value = message
                ui._submit(None)
            self.assertTrue(self.agent.dialogue.summary)
            ui.input.value = command
            ui._submit(None)
            self.assertFalse(self.memory.load_memory_variables()["facts"])
            self.assertFalse(self.agent.dialogue.summary or self.agent.dialogue.messages())

    def test_history_size_and_window_validation(self):
        for invalid in (0, 9, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                DialogueMemory(invalid)
        self.agent.ask("x" * 12000)
        self.assertLessEqual(len(self.agent.dialogue.messages()[0].content), 2400)

    def test_extracted_level_applies_to_same_turn(self):
        patch = {"updates": [{"key": "level", "value": "эксперт", "evidence": "Я эксперт"}]}
        self.agent.extract_chain = RunnableLambda(lambda _: patch)
        self.agent.ask("Я эксперт. Что такое SCD2?")
        self.assertEqual(self.events[-1]["teaching_mode"], "advanced")
