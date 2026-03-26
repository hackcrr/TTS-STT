#!/usr/bin/env python3
"""Minimal MCP stdio server that wraps the local TTS/STT HTTP APIs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

from env_utils import env_int, load_env_files


ROOT_DIR = Path(__file__).resolve().parent
load_env_files(ROOT_DIR)

TTS_PORT = env_int("TTS_PORT", 5000)
STT_PORT = env_int("STT_PORT", 5001)
MCP_TTS_BASE_URL = os.environ.get("MCP_TTS_BASE_URL", f"http://127.0.0.1:{TTS_PORT}").rstrip("/")
MCP_STT_BASE_URL = os.environ.get("MCP_STT_BASE_URL", f"http://127.0.0.1:{STT_PORT}").rstrip("/")

SERVER_INFO = {"name": "tts-stt-mcp", "version": "1.0.0"}


class MCPError(Exception):
    pass


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None

    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def write_response(message_id: Any, result: dict[str, Any]) -> None:
    write_message({"jsonrpc": "2.0", "id": message_id, "result": result})


def write_error(message_id: Any, code: int, message: str) -> None:
    write_message({"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}})


def http_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = requests.request(method=method, url=url, timeout=120, **kwargs)
    except requests.RequestException as exc:
        raise MCPError(f"Request failed: {exc}") from exc

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    if not response.ok:
        message = data.get("error") if isinstance(data, dict) else None
        raise MCPError(message or f"HTTP {response.status_code}: {response.text}")
    return data


def make_absolute_download_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"{MCP_TTS_BASE_URL}{url}"
    return f"{MCP_TTS_BASE_URL}/{url}"


def normalize_download_urls(payload: Any) -> Any:
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "download_url" and isinstance(value, str):
                normalized[key] = make_absolute_download_url(value)
            else:
                normalized[key] = normalize_download_urls(value)
        return normalized
    if isinstance(payload, list):
        return [normalize_download_urls(item) for item in payload]
    return payload


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_voices",
            "description": "List available TTS voices.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "synthesize_text",
            "description": "Synthesize text into one or more MP3 files.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "topic": {"type": "string"},
                    "voice": {"type": "string"},
                    "rate": {"type": "string"},
                    "pitch": {"type": "string"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "synthesize_dialogue",
            "description": "Synthesize a dialogue script into one MP3 file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "topic": {"type": "string"},
                    "maleVoice": {"type": "string"},
                    "femaleVoice": {"type": "string"},
                    "rate": {"type": "string"},
                    "pitch": {"type": "string"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_sessions",
            "description": "List generated synthesis sessions.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "delete_session",
            "description": "Delete a synthesis session by topic.",
            "inputSchema": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
                "additionalProperties": False,
            },
        },
        {
            "name": "transcribe_file",
            "description": "Upload a local audio file to the STT service.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["file_path"],
                "additionalProperties": False,
            },
        },
        {
            "name": "transcribe_url",
            "description": "Ask the STT service to transcribe a remote audio URL.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    ]


def tool_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    normalized = normalize_download_urls(payload)
    return {
        "content": [{"type": "text", "text": json.dumps(normalized, ensure_ascii=False, indent=2)}],
        "structuredContent": normalized,
        "isError": is_error,
    }


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "list_voices":
        return tool_result(http_json("GET", f"{MCP_TTS_BASE_URL}/api/voices"))

    if name == "synthesize_text":
        payload = {
            "text": arguments["text"],
            "topic": arguments.get("topic"),
            "voice": arguments.get("voice", "jenny"),
            "rate": arguments.get("rate", "+0%"),
            "pitch": arguments.get("pitch", "+0Hz"),
        }
        return tool_result(http_json("POST", f"{MCP_TTS_BASE_URL}/api/synthesize", json=payload))

    if name == "synthesize_dialogue":
        payload = {
            "text": arguments["text"],
            "topic": arguments.get("topic"),
            "maleVoice": arguments.get("maleVoice", "guy"),
            "femaleVoice": arguments.get("femaleVoice", "jenny"),
            "rate": arguments.get("rate", "+0%"),
            "pitch": arguments.get("pitch", "+0Hz"),
        }
        return tool_result(http_json("POST", f"{MCP_TTS_BASE_URL}/api/dialogue", json=payload))

    if name == "list_sessions":
        return tool_result(http_json("GET", f"{MCP_TTS_BASE_URL}/api/sessions"))

    if name == "delete_session":
        topic = arguments["topic"].strip()
        if not topic:
            raise MCPError("topic is required.")
        return tool_result(http_json("DELETE", f"{MCP_TTS_BASE_URL}/api/sessions/{topic}"))

    if name == "transcribe_file":
        file_path = Path(arguments["file_path"]).expanduser()
        if not file_path.exists():
            raise MCPError(f"File not found: {file_path}")

        with file_path.open("rb") as file_handle:
            files = {"file": (file_path.name, file_handle)}
            data = {}
            if arguments.get("language"):
                data["language"] = arguments["language"]
            return tool_result(http_json("POST", f"{MCP_STT_BASE_URL}/api/stt", files=files, data=data))

    if name == "transcribe_url":
        payload = {"url": arguments["url"]}
        if arguments.get("language"):
            payload["language"] = arguments["language"]
        return tool_result(http_json("POST", f"{MCP_STT_BASE_URL}/api/stt/url", json=payload))

    raise MCPError(f"Unknown tool: {name}")


def handle_request(message: dict[str, Any]) -> None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        requested_version = params.get("protocolVersion") or "2024-11-05"
        write_response(
            message_id,
            {
                "protocolVersion": requested_version,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )
        return

    if method == "notifications/initialized":
        return

    if method == "ping":
        write_response(message_id, {})
        return

    if method == "tools/list":
        write_response(message_id, {"tools": list_tools()})
        return

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(name, arguments)
        except MCPError as exc:
            write_response(message_id, tool_result({"error": str(exc)}, is_error=True))
            return
        write_response(message_id, result)
        return

    if message_id is not None:
        write_error(message_id, -32601, f"Method not found: {method}")


def main() -> int:
    while True:
        message = read_message()
        if message is None:
            return 0

        try:
            handle_request(message)
        except Exception as exc:
            message_id = message.get("id")
            if message_id is not None:
                write_error(message_id, -32000, str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
