"""Regression checks for installed imports, relocated resources and launchers."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dwh_agent.paths import ROOT, MEMORY_FILE
from dwh_agent.restart_demo import run_restart_demo


class ProjectLayoutTests(unittest.TestCase):
    def run_python(self, arguments, cwd):
        result = subprocess.run(
            [sys.executable, *arguments], cwd=cwd, capture_output=True,
            text=True, encoding="utf-8", timeout=30,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_installed_agents_load_resources_outside_repository(self):
        code = """
from pathlib import Path
from dwh_agent.transport import Client
from dwh_agent.practicum.assistant import Agent
from dwh_agent.fact_agent import FactAgent
from dwh_agent.fact_memory import FileFactMemory
client = Client('local-4b')
for variant in ('baseline', 'improved', 'general'):
    assert Agent(client, prompt=variant).messages
agent = FactAgent(FileFactMemory(Path('test_memory.json')))
assert agent.extract_chain and agent.answer_chain
"""
        with tempfile.TemporaryDirectory() as directory:
            self.run_python(["-c", code], directory)

    def test_lab_entrypoints_work_from_their_own_directory(self):
        scripts = [
            "labs/01_dwh_agent/run_local.py", "labs/01_dwh_agent/assistant.py",
            "labs/02_fact_memory/memory_session.py",
            "labs/02_fact_memory/verify_memory_restart.py",
        ]
        for relative in scripts:
            script = ROOT / relative
            with self.subTest(script=relative):
                result = self.run_python([script.name, "--help"], script.parent)
                self.assertIn("usage:", result.stdout)

    def test_demo_cannot_reset_current_or_legacy_personal_memory(self):
        with patch("dwh_agent.restart_demo.FileFactMemory") as memory:
            for path in (MEMORY_FILE, ROOT / "memory.json"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    run_restart_demo(path, start_server=False)
            memory.assert_not_called()
