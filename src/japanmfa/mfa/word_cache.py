"""Exact successful native word results, separated by model/adapter identity."""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
from pathlib import Path


class WordCache:
    def __init__(self, root):
        Path(root).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(Path(root) / "native-words.sqlite3", timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS words (identity TEXT, stage TEXT, request TEXT, payload TEXT, sha TEXT, PRIMARY KEY(identity,stage,request))")
        self.hits = self.misses = 0

    def get(self, identity, stage, request):
        key = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        row = self.db.execute("SELECT payload,sha FROM words WHERE identity=? AND stage=? AND request=?", (identity,stage,key)).fetchone()
        if row is None and stage in {"accent", "g2p"}:
            previous = os.environ.get("JAPANMFA_ACCENT_COMPAT_IDENTITY" if stage == "accent"
                                      else "JAPANMFA_G2P_COMPAT_IDENTITY")
            if previous and previous != identity:
                row = self.db.execute("SELECT payload,sha FROM words WHERE identity=? AND stage=? AND request=?",
                                      (previous,stage,key)).fetchone()
        if row and hashlib.sha256(row[0].encode()).hexdigest() == row[1]:
            self.hits += 1
            return json.loads(row[0])
        self.misses += 1
        return None

    def put(self, identity, stage, request, value):
        key = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
        self.db.execute("INSERT OR REPLACE INTO words VALUES(?,?,?,?,?)", (identity,stage,key,payload,hashlib.sha256(payload.encode()).hexdigest()))


    def commit(self):
        self.db.commit()

    def close(self):
        self.db.close()
