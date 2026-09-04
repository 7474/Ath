#!/usr/bin/env python3
"""Baronh translation via an OpenAI-compatible Chat Completions API.

Grammar and lexicon are too large to dump into every prompt. This module:

1. Retrieves relevant cards/entries locally (keyword search).
2. Calls Chat Completions (any Base URL).
3. If the server supports tools, the model can pull more cards itself.
4. After translation, maps Ath webfont keys to IPA for a *separate* TTS step.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import ath_openai as api
import ath_retrieve as kr

SYSTEM_PROMPT = """You translate Japanese or English into Baronh (アーヴ語).
Write Baronh using the Aarth webfont keys: lowercase phonemes, A=ai, I=au, E=eu.
Do not invent a full dictionary. Use only retrieved lexicon/grammar, tool results, or
widely attested public forms. If a word is missing, keep it as a phonetic proper noun
and say so in notesJa.

Reply with JSON only:
{"baronh":"...","ipa":null,"notesJa":["..."],"used":["lexicon/grammar ids"]}
Leave ipa null; the client fills IPA from webfont keys.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_lexicon",
            "description": "Search the local Baronh seed lexicon by Japanese, English, or Baronh.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_grammar",
            "description": "Search grammar cards (cases, verbs, postpositions, TTS pipeline).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_phonemes",
            "description": "Return Ath webfont key to IPA mappings for speech synthesis.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def run_tool(name: str, arguments: dict) -> str:
    query = str(arguments.get("query") or "")
    if name == "search_lexicon":
        return json.dumps(kr.search_lexicon(query), ensure_ascii=False)
    if name == "search_grammar":
        return json.dumps(kr.search_grammar(query), ensure_ascii=False)
    if name == "get_phonemes":
        return json.dumps(kr.load_phonemes(), ensure_ascii=False)
    return json.dumps({"error": f"unknown tool {name}"})


def _parse_content(content: str) -> dict:
    raw = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fenced:
        raw = fenced.group(1).strip()
    data = json.loads(raw)
    baronh = str(data.get("baronh") or "")
    return {
        "baronh": baronh,
        "ipa": kr.keys_to_ipa(baronh),
        "notesJa": [str(n) for n in (data.get("notesJa") or [])],
        "used": data.get("used") or [],
    }


def translate(
    text: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    use_tools: bool = True,
    max_rounds: int = 6,
    urlopen=None,
) -> dict:
    retrieved = kr.retrieve(text)
    trace = [{"step": "retrieve", "grammar": [g["id"] for g in retrieved["grammar"]],
              "lexicon": [e.get("baronh") for e in retrieved["lexicon"]]}]
    user_payload = {"text": text, "retrieved": {
        "grammar": retrieved["grammar"],
        "lexicon": retrieved["lexicon"],
    }}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
    tools = TOOLS if use_tools else None
    last_error = None
    for _round in range(max_rounds):
        try:
            payload = api.chat_completions(
                messages,
                base_url=base_url,
                api_key=api_key,
                model=model,
                tools=tools,
                urlopen=urlopen,
            )
        except api.OpenAICompatError as exc:
            if tools and _round == 0:
                tools = None
                last_error = str(exc)
                trace.append({"step": "tools-unsupported", "error": last_error})
                continue
            raise
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            messages.append(message)
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(name, args)
                trace.append({"step": "tool", "name": name, "arguments": args})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or name,
                    "content": result,
                })
            continue
        content = message.get("content") or ""
        parsed = _parse_content(content)
        parsed["trace"] = trace
        parsed["baseUrl"] = api.normalize_openai_base_url(base_url)
        parsed["speechUrl"] = api.audio_speech_url(base_url)
        return parsed
    raise api.OpenAICompatError("model did not finish translation")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Translate into Baronh via an OpenAI-compatible API, then show IPA for TTS."
    )
    parser.add_argument("text", nargs="?", help="Input text (stdin if omitted)")
    parser.add_argument(
        "--api-base",
        default=os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or api.DEFAULT_OPENAI_BASE_URL,
        help="OpenAI-compatible API root (default official OpenAI /v1)",
    )
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL") or api.DEFAULT_CHAT_MODEL)
    parser.add_argument("--no-tools", action="store_true", help="Do not advertise tools (compat servers without tool-calling)")
    parser.add_argument(
        "--speak",
        action="store_true",
        help="POST IPA to the same Base URL /audio/speech (often missing on compatible servers)",
    )
    parser.add_argument("--speech-out", default="", help="Write speech audio bytes to this path")
    args = parser.parse_args(argv)
    text = args.text if args.text is not None else sys.stdin.read()
    result = translate(
        text,
        base_url=args.api_base,
        api_key=args.api_key,
        model=args.model,
        use_tools=not args.no_tools,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.speak:
        audio = api.audio_speech(
            result["ipa"] or result["baronh"],
            base_url=args.api_base,
            api_key=args.api_key,
        )
        path = args.speech_out or "baronh.mp3"
        Path = __import__("pathlib").Path
        Path(path).write_bytes(audio)
        print(f"wrote {path} ({len(audio)} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
