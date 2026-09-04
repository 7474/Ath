#!/usr/bin/env python3
"""OpenAI-compatible mock: /v1/chat/completions and optional /v1/audio/speech."""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _cors(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")


def make_handler(state: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            _cors(self)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                payload = {}
            state["last"] = {"path": self.path, "payload": payload}
            if self.path.endswith("/audio/speech"):
                audio = b"ID3fake-speech"
                self.send_response(200)
                _cors(self)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio)))
                self.end_headers()
                self.wfile.write(audio)
                return
            note = "種辞書の gereulach を使い、互換API経由で翻訳しました。"
            body = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "baronh": "gereulach éü",
                            "notesJa": [note],
                            "used": ["gereulach", "postpositions"],
                        }, ensure_ascii=False)
                    }
                }]
            }
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            _cors(self)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


def start_server(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, dict[str, Any]]:
    state: dict[str, Any] = {"last": None}
    server = ThreadingHTTPServer((host, port), make_handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server, _state = start_server(args.host, args.port)
    print(f"openai-compat mock on http://{args.host}:{server.server_address[1]}/v1", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
