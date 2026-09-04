#!/usr/bin/env python3
"""OpenAI-compatible HTTP helpers (Chat Completions and optional TTS).

Official OpenAI is ``https://api.openai.com/v1``. Compatible servers
(Ollama, Groq, OpenRouter, vLLM, LM Studio, etc.) are selected by Base URL.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_SPEECH_MODEL = "tts-1"


def normalize_openai_base_url(url: str | None) -> str:
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raw = (
            os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
            or DEFAULT_OPENAI_BASE_URL
        )
        raw = raw.strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.path in ("", "/"):
        raw = raw.rstrip("/") + "/v1"
    return raw


def chat_completions_url(base_url: str | None) -> str:
    return normalize_openai_base_url(base_url) + "/chat/completions"


def audio_speech_url(base_url: str | None) -> str:
    return normalize_openai_base_url(base_url) + "/audio/speech"


def _headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


class OpenAICompatError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _urlopen_json(
    url: str,
    payload: dict,
    *,
    api_key: str | None,
    timeout: float,
    urlopen=None,
) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=_headers(api_key), method="POST")
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            err = json.loads(detail) if detail else {}
            message = err.get("error", {}).get("message") or detail or str(exc)
        except json.JSONDecodeError:
            message = detail or str(exc)
        raise OpenAICompatError(str(message), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise OpenAICompatError(str(exc.reason or exc)) from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise OpenAICompatError(f"non-JSON response: {exc}") from exc


def chat_completions(
    messages: list[dict],
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0,
    timeout: float = 60,
    urlopen=None,
) -> dict:
    body: dict = {
        "model": model or os.environ.get("OPENAI_MODEL") or DEFAULT_CHAT_MODEL,
        "temperature": temperature,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    return _urlopen_json(
        chat_completions_url(base_url),
        body,
        api_key=api_key,
        timeout=timeout,
        urlopen=urlopen,
    )


def audio_speech(
    input_text: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    voice: str = "alloy",
    timeout: float = 60,
    urlopen=None,
) -> bytes:
    """POST /v1/audio/speech. Many compatible servers do not implement this."""
    body = {
        "model": model or DEFAULT_SPEECH_MODEL,
        "voice": voice,
        "input": input_text,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        audio_speech_url(base_url),
        data=data,
        headers=_headers(api_key),
        method="POST",
    )
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise OpenAICompatError(detail or str(exc), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise OpenAICompatError(str(exc.reason or exc)) from exc
