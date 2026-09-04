#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.lexicon import load_lexicon
from baronh.server import make_handler
from http.server import ThreadingHTTPServer


class AgentHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()
        handler = make_handler(cls.lex)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _conn(self) -> HTTPConnection:
        return HTTPConnection("127.0.0.1", self.port, timeout=8)

    def test_health(self):
        conn = self._conn()
        conn.request("GET", "/api/health")
        res = conn.getresponse()
        body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 200)
        self.assertTrue(body["ok"])
        self.assertGreater(body["entries"], 2000)
        self.assertIn("agent", body["engines"])

    def test_synonyms_endpoint(self):
        conn = self._conn()
        conn.request("GET", "/api/synonyms?q=%E5%85%89")
        res = conn.getresponse()
        body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 200)
        self.assertTrue(any(hit["lemma"] == "sairiac" for hit in body["hits"]))

    def test_translate_agent_local_synonym(self):
        payload = json.dumps({
            "text": "星たちの光を見ます",
            "source_lang": "ja",
            "target_lang": "baronh",
            "engine": "agent",
        }).encode("utf-8")
        conn = self._conn()
        conn.request(
            "POST",
            "/api/translate",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        res = conn.getresponse()
        body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 200, body)
        self.assertEqual(body["engine"], "agent")
        self.assertTrue(any(item["from"] == "光" for item in body["substitutions"]))
        self.assertIn("sairiac", json.dumps(body, ensure_ascii=False).lower())
        self.assertNotIn("光", body["text"])

    def test_translate_rules_still_leaves_unknown(self):
        payload = json.dumps({
            "text": "星たちの光を見ます",
            "source_lang": "ja",
            "target_lang": "baronh",
            "engine": "local",
        }).encode("utf-8")
        conn = self._conn()
        conn.request(
            "POST",
            "/api/translate",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        res = conn.getresponse()
        body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 200, body)
        self.assertIn("光", body["text"])

    def test_cors_preflight(self):
        conn = self._conn()
        conn.request(
            "OPTIONS",
            "/api/translate",
            headers={"Origin": "https://7474.github.io", "Access-Control-Request-Method": "POST"},
        )
        res = conn.getresponse()
        res.read()
        self.assertEqual(res.status, 204)
        self.assertEqual(res.getheader("Access-Control-Allow-Origin"), "*")

    def test_rejects_empty(self):
        conn = self._conn()
        conn.request(
            "POST",
            "/api/translate",
            body=b'{"text":""}',
            headers={"Content-Type": "application/json"},
        )
        res = conn.getresponse()
        self.assertEqual(res.status, 400)


if __name__ == "__main__":
    unittest.main()
