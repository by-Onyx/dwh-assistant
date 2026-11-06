"""Local dense retrieval for the DWH lab. SQLite stores passages and unit vectors."""
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import textwrap
from urllib.request import Request, urlopen

from .paths import BACKENDS_CONFIG


class QwenEncoder:
    def __init__(self):
        config = json.loads(BACKENDS_CONFIG.read_text(encoding="utf-8"))["local-embedding"]
        self.url = config["base_url"] + "/embeddings"
        self.model = config["model"]

    def encode(self, text, *, query=False):
        if query:
            text = "Instruct: Find the DWH handbook passage that answers the user's question.\nQuery: " + text
        payload = json.dumps({"model": self.model, "input": text}).encode()
        req = Request(self.url, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=90) as response:
            return json.load(response)["data"][0]["embedding"]


@dataclass(frozen=True)
class Hit:
    source: str
    text: str
    score: float


def passages(folder):
    """Index titled Markdown sections, splitting long sections at word boundaries."""
    for path in sorted(Path(folder).glob("*.md")):
        parts = re.split(r"^## (.+?)\s*$", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        for heading, body in zip(parts[1::2], parts[2::2], strict=True):
            chunks = textwrap.wrap(" ".join(body.split()), width=900)
            for number, chunk in enumerate(chunks, 1):
                source = f"{path.name} — {heading.strip()}"
                if len(chunks) > 1:
                    source += f" ({number}/{len(chunks)})"
                yield source, chunk


def unit_vector(values):
    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Энкодер вернул пустой или некорректный вектор")
    return [value / norm for value in values]


class VectorIndex:
    def __init__(self, path, encoder):
        self.path = Path(path)
        self.encoder = encoder

    def sync(self, folder):
        docs = list(passages(folder))
        if not docs:
            raise ValueError("В базе знаний нет непустых разделов Markdown с заголовком ##")
        fingerprint = hashlib.sha256(json.dumps([self.encoder.model, docs]).encode()).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=90)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS metadata (fingerprint TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS passages (source TEXT, body TEXT, vector TEXT)")
            if db.execute("SELECT fingerprint FROM metadata").fetchone() == (fingerprint,):
                return len(docs)
            # Replace the whole snapshot in one transaction, including removed sections.
            rows = []
            for source, body in docs:
                vector = unit_vector(self.encoder.encode(source + "\n" + body))
                rows.append((source, body, json.dumps(vector)))
            db.execute("DELETE FROM passages")
            db.executemany("INSERT INTO passages VALUES (?, ?, ?)", rows)
            db.execute("DELETE FROM metadata")
            db.execute("INSERT INTO metadata VALUES (?)", (fingerprint,))
        return len(docs)

    def search(self, question, *, limit=2, min_score=0.56):
        query = unit_vector(self.encoder.encode(question, query=True))
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT source, body, vector FROM passages")
            hits = []
            for source, body, vector in rows:
                score = math.sumprod(query, json.loads(vector))
                if score >= min_score:
                    hits.append(Hit(source, body, score))
        return sorted(hits, key=lambda hit: -hit.score)[:limit]
