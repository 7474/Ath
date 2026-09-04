"""静的サイトと翻訳エージェント API を同じプロセスで出す。"""

from __future__ import annotations

import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from baronh.agent import AgentModelRequired, model_configured, translate_agent
from baronh.ingest import write_lexicon
from baronh.lexicon import Lexicon, load_lexicon
from baronh.paths import DATA_DIR, ROOT_DIR, WEB_DIR
from baronh.synonyms import find_synonyms, format_hits
from baronh.translate import translate
from baronh.vectordb import VECTOR_DIM, get_index, hit_to_dict
from baronh.openai_backend import DEFAULT_CHAT_MODEL

MAX_BODY = 64 * 1024


def _cors_origin() -> str:
    return os.environ.get("BARONH_CORS_ORIGIN", "*").strip() or "*"


class TranslatorHandler(SimpleHTTPRequestHandler):
    lexicon: Lexicon
    chat_once: Any = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

    def log_message(self, fmt: str, *log_args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % log_args))

    def end_headers(self) -> None:
        if self.path.startswith("/api/") or self.headers.get("Origin"):
            origin = _cors_origin()
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            if origin != "*":
                self.send_header("Vary", "Origin")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        rel = unquote(parsed.path)
        if rel.startswith("/data/"):
            web_target = (WEB_DIR / rel.lstrip("/")).resolve()
            if str(web_target).startswith(str(WEB_DIR.resolve())) and web_target.is_file():
                return str(web_target)
            target = (DATA_DIR / rel[len("/data/") :]).resolve()
            if str(target).startswith(str(DATA_DIR.resolve())) and target.is_file():
                return str(target)
        if rel.startswith("/font/"):
            name = rel[len("/font/") :]
            target = (ROOT_DIR / name).resolve()
            if str(target).startswith(str(ROOT_DIR.resolve())) and target.is_file():
                return str(target)
        return super().translate_path(path)

    def do_OPTIONS(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.send_response(204)
            self.end_headers()
            return
        self.send_error(404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "entries": len(self.lexicon.entries),
                    "engines": ["local", "agent", "openai"],
                    "vector_dim": VECTOR_DIM,
                    "model": model_configured(),
                    "chat_model": os.environ.get("OPENAI_CHAT_MODEL") or DEFAULT_CHAT_MODEL,
                }
            )
            return
        if parsed.path == "/api/synonyms":
            query = (parse_qs(parsed.query).get("q") or [""])[0]
            hits = find_synonyms(query, self.lexicon)
            self._send_json({"query": query, "hits": format_hits(hits)})
            return
        if parsed.path == "/api/search":
            query = (parse_qs(parsed.query).get("q") or [""])[0]
            try:
                limit = int((parse_qs(parsed.query).get("limit") or ["8"])[0])
            except ValueError:
                limit = 8
            limit = max(1, min(limit, 16))
            hits = get_index(self.lexicon).search(query, limit=limit)
            self._send_json({"query": query, "hits": [hit_to_dict(hit) for hit in hits]})
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/translate":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._send_json({"error": "payload too large"}, status=413)
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "invalid json"}, status=400)
            return
        if not isinstance(payload, dict):
            self._send_json({"error": "object required"}, status=400)
            return
        text = str(payload.get("text") or "").strip()
        if not text:
            self._send_json({"error": "text required"}, status=400)
            return
        source = str(payload.get("source_lang") or "auto")
        target = str(payload.get("target_lang") or "auto")
        engine = str(payload.get("engine") or "agent")
        if source not in {"auto", "ja", "en", "baronh"} or target not in {"auto", "ja", "en", "baronh"}:
            self._send_json({"error": "invalid lang"}, status=400)
            return
        try:
            result = run_translate(
                self.lexicon,
                text,
                source_lang=source,
                target_lang=target,
                engine=engine,
                chat_once=self.chat_once,
            )
        except AgentModelRequired as exc:
            self._send_json({"error": str(exc)}, status=503)
            return
        except Exception as exc:  # noqa: BLE001 — API 境界でメッセージを返す
            self._send_json({"error": str(exc)}, status=500)
            return
        self._send_json(result.to_dict())

    def _send_json(self, body: dict[str, Any], *, status: int = 200) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_translate(
    lexicon: Lexicon,
    text: str,
    *,
    source_lang: str = "auto",
    target_lang: str = "auto",
    engine: str = "agent",
    chat_once: Any = None,
) -> Any:
    if engine == "local":
        return translate(text, lexicon, source_lang=source_lang, target_lang=target_lang)
    if engine == "openai":
        from baronh.openai_backend import translate_openai

        return translate_openai(text, lexicon, source_lang=source_lang, target_lang=target_lang)
    return translate_agent(
        text,
        lexicon,
        source_lang=source_lang,
        target_lang=target_lang,
        chat_once=chat_once,
    )


def make_handler(lexicon: Lexicon, *, chat_once: Any = None) -> type[TranslatorHandler]:
    class BoundHandler(TranslatorHandler):
        pass

    BoundHandler.lexicon = lexicon
    BoundHandler.chat_once = staticmethod(chat_once) if chat_once is not None else None
    return BoundHandler


def serve(host: str = "127.0.0.1", port: int = 8765, *, lexicon: Lexicon | None = None) -> None:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    loaded = lexicon or load_lexicon()
    write_lexicon(loaded, WEB_DIR / "data" / "lexicon.json")
    handler = make_handler(loaded)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"アーヴ語とアース: {url}", file=sys.stderr)
    print(f"翻訳: {url}web/", file=sys.stderr)
    print(f"エージェント API: {url}api/translate", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
