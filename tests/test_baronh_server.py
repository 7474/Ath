#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baronh.lexicon import load_lexicon
from baronh.server import make_handler


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
        self.assertEqual(body["vector_dim"], 512)
        self.assertIn("model", body)
        lang_ids = {row["id"] for row in body["languages"]}
        self.assertIn("mina", lang_ids)
        self.assertIn("baronh", lang_ids)

    def test_synonyms_endpoint(self):
        conn = self._conn()
        conn.request("GET", "/api/synonyms?q=%E5%85%89")
        res = conn.getresponse()
        body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 200)
        self.assertTrue(any(hit["lemma"] == "sairiac" for hit in body["hits"]))

    def test_search_endpoint(self):
        conn = self._conn()
        conn.request("GET", "/api/search?q=%E5%85%89")
        res = conn.getresponse()
        body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 200)
        self.assertTrue(any(hit["lemma"] == "sairiac" for hit in body["hits"]))
        self.assertFalse(any("凝集光銃" in (hit.get("gloss_ja") or "") for hit in body["hits"]))

    def test_translate_agent_requires_model(self):
        payload = json.dumps({
            "text": "星たちの光を見ます",
            "source_lang": "ja",
            "target_lang": "baronh",
            "engine": "agent",
        }).encode("utf-8")
        env = {"OPENAI_API_KEY": "", "OPENAI_BASE_URL": "", "OPENAI_API_BASE": ""}
        with mock.patch.dict("os.environ", env, clear=False):
            conn = self._conn()
            conn.request(
                "POST",
                "/api/translate",
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            res = conn.getresponse()
            body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 503, body)
        self.assertIn("生成 AI", body["error"])

    def test_translate_agent_stream_requires_model(self):
        payload = json.dumps({
            "text": "星たちの光を見ます",
            "source_lang": "ja",
            "target_lang": "baronh",
            "engine": "agent",
            "stream": True,
        }).encode("utf-8")
        env = {"OPENAI_API_KEY": "", "OPENAI_BASE_URL": "", "OPENAI_API_BASE": ""}
        with mock.patch.dict("os.environ", env, clear=False):
            conn = self._conn()
            conn.request(
                "POST",
                "/api/translate",
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            res = conn.getresponse()
            body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 503, body)
        self.assertIn("生成 AI", body["error"])
        self.assertNotIn("ndjson", (res.getheader("Content-Type") or "").lower())

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


    def test_translate_mina_pack(self):
        payload = json.dumps({
            "text": "私はミーナです",
            "source_lang": "ja",
            "target_lang": "mina",
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
        self.assertEqual(body["text"], "na ya minde.")
        self.assertEqual(body["engine"], "transfer")
        self.assertEqual(body["target_lang"], "mina")

    def test_translate_mina_without_model(self):
        payload = json.dumps({
            "text": "私はミーナです",
            "source_lang": "ja",
            "target_lang": "mina",
            "engine": "agent",
            "stream": True,
        }).encode("utf-8")
        env = {"OPENAI_API_KEY": "", "OPENAI_BASE_URL": "", "OPENAI_API_BASE": ""}
        with mock.patch.dict("os.environ", env, clear=False):
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
        self.assertEqual(body["text"], "na ya minde.")
        self.assertEqual(body["engine"], "transfer")

    def test_languages_endpoint(self):
        conn = self._conn()
        conn.request("GET", "/api/languages")
        res = conn.getresponse()
        body = json.loads(res.read().decode("utf-8"))
        self.assertEqual(res.status, 200)
        ids = {row["id"] for row in body["languages"]}
        self.assertIn("mina", ids)
        self.assertIn("ja", ids)
        self.assertIn("baronh", ids)


class AgentHttpFakeChatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lexicon()

        def chat_once(payload):
            return {"choices": [{"message": {"content": "gereulacr sairiac mire."}}]}

        handler = make_handler(cls.lex, chat_once=chat_once)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_translate_agent_with_model(self):
        payload = json.dumps({
            "text": "星たちの光を見ます",
            "source_lang": "ja",
            "target_lang": "baronh",
            "engine": "agent",
        }).encode("utf-8")
        conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
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
        self.assertEqual(body["source_text"], "星たちの光を見ます")
        self.assertIn("sairiac", body["text"])
        self.assertNotIn("光", body["text"])

    def test_translate_agent_stream_progress(self):
        payload = json.dumps({
            "text": "星たちの光を見ます",
            "source_lang": "ja",
            "target_lang": "baronh",
            "engine": "agent",
            "stream": True,
        }).encode("utf-8")
        conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
        conn.request(
            "POST",
            "/api/translate",
            body=payload,
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        )
        res = conn.getresponse()
        raw = res.read().decode("utf-8")
        self.assertEqual(res.status, 200, raw)
        self.assertIn("ndjson", (res.getheader("Content-Type") or "").lower())
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        self.assertTrue(any(ev.get("type") == "progress" and ev.get("phase") == "chat" for ev in events), events)
        self.assertTrue(any(ev.get("type") == "progress" and ev.get("phase") == "draft" for ev in events), events)
        result = next(ev for ev in events if ev.get("type") == "result")
        self.assertIn("sairiac", result["result"]["text"])
        self.assertNotIn("光", result["result"]["text"])


if __name__ == "__main__":
    unittest.main()
