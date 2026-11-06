from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from langchain_core.runnables import RunnableLambda

from dwh_agent.fact_agent import FactAgent
from dwh_agent.fact_memory import FileFactMemory
from dwh_agent.notebook_ui import NotebookChat
from dwh_agent.rag import Hit, VectorIndex, passages


class VectorIndexTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.handbook = self.folder / "rules.md"
        self.handbook.write_text("## A\nAlpha rule\n\n## B\nBeta rule", encoding="utf-8")
        self.encoder = Mock(model="encoder-v1")
        self.encoder.encode.side_effect = [[3, 0], [0, 4]]
        self.index = VectorIndex(self.folder / "knowledge.sqlite3", self.encoder)
        self.assertEqual(self.index.sync(self.folder), 2)

    def test_query_and_documents_share_normalized_vector_space(self):
        self.encoder.encode.side_effect = [[0, 20], [-2, -3]]
        hit, = self.index.search("парафраз без общих слов")
        self.assertEqual((hit.source, hit.text, hit.score), ("rules.md — B", "Beta rule", 1))
        self.encoder.encode.assert_called_with("парафраз без общих слов", query=True)
        self.assertEqual(self.index.search("другая тема"), [])

    def test_reopen_cache_and_replace_old_sections(self):
        reopened = VectorIndex(self.index.path, self.encoder)
        self.assertEqual(reopened.sync(self.folder), 2)
        self.assertEqual(self.encoder.encode.call_count, 2)
        self.handbook.write_text("## New\nUpdated rule", encoding="utf-8")
        self.encoder.encode.side_effect = [[1, 0], [1, 0]]
        self.assertEqual(reopened.sync(self.folder), 1)
        self.assertEqual([h.text for h in reopened.search("new")], ["Updated rule"])

    def test_invalid_embedding_cannot_destroy_last_working_snapshot(self):
        self.handbook.write_text("## New\nBroken", encoding="utf-8")
        self.encoder.encode.side_effect = [[0, 0], [1, 0]]
        with self.assertRaises(ValueError):
            self.index.sync(self.folder)
        self.assertEqual(self.index.search("old")[0].text, "Alpha rule")

    def test_long_sections_have_bounded_numbered_passages(self):
        self.handbook.write_text("## Long\n" + "слово " * 400, encoding="utf-8")
        chunks = list(passages(self.folder))
        self.assertGreater(len(chunks), 1)
        self.assertEqual(len({source for source, _ in chunks}), len(chunks))
        self.assertTrue(all(len(body) <= 900 for _, body in chunks))


class RagChatTests(unittest.TestCase):
    def test_regular_turns_retrieve_fresh_context_and_commands_bypass_search(self):
        with TemporaryDirectory() as temp:
            extracts, replies, events = [], [], []
            def capture(target, reply):
                def invoke(prompt):
                    target.append(prompt.to_messages())
                    return reply
                return RunnableLambda(invoke)

            retriever = Mock()
            retriever.search.side_effect = [[Hit("manual.md — A", "private_handbook_marker", 0.8)], []]
            agent = FactAgent(FileFactMemory(Path(temp) / "facts.json"),
                              extractor=capture(extracts, '{"updates":[]}'),
                              responder=capture(replies, "Ответ"), retriever=retriever,
                              summarizer=RunnableLambda(lambda _: "Сводка"), on_event=events.append)
            agent.ask("/remember level новичок")
            agent.ask("/practice")
            retriever.search.assert_not_called()
            ui = NotebookChat()
            ui.attach(agent)
            ui.input.value = "Расскажи про возвраты"
            ui._submit(None)
            self.assertIn("manual.md — A", ui.chat_output.outputs[-1]["text"])
            self.assertIn("private_handbook_marker", replies[0][-1].content)
            self.assertNotIn("private_handbook_marker", str(extracts))
            result = agent.ask("А если срок прошёл?")
            self.assertEqual(result["sources"], [])
            self.assertNotIn("private_handbook_marker", replies[1][-1].content)
            self.assertEqual(retriever.search.call_args.args, ("Расскажи про возвраты\nА если срок прошёл?",))
            self.assertEqual([e["sources"] for e in events if e["event"] == "rag_retrieved"], [["manual.md — A"], []])
            self.assertEqual(result["facts"], {"level": "новичок"})
