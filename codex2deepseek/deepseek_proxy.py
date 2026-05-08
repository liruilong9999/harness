#!/usr/bin/env python3
"""Codex <-> DeepSeek local proxy.

This server exposes a small OpenAI Responses API compatible surface for Codex
and forwards requests to DeepSeek's chat.completions endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error, request


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 50010
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_PROXY_AUTH = "local-deepseek-proxy"


def now_ts() -> int:
    return int(time.time())


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def discover_usage_text_path() -> Path | None:
    txt_files = sorted(SCRIPT_DIR.glob("*.txt"))
    if not txt_files:
        return None
    return txt_files[0]


def parse_key_value_from_text(text: str, key: str) -> str | None:
    pattern = rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"'
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def normalize_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def maybe_parse_json_string(value: str) -> Any:
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def decode_nested_json_strings(value: Any) -> Any:
    if isinstance(value, str):
        parsed = maybe_parse_json_string(value)
        if parsed is value:
            return value
        return decode_nested_json_strings(parsed)
    if isinstance(value, list):
        return [decode_nested_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: decode_nested_json_strings(item) for key, item in value.items()}
    return value


def parse_auth_file(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    token = data.get("OPENAI_API_KEY")
    return token if isinstance(token, str) and token else None


@dataclass
class ProxyConfig:
    host: str
    port: int
    deepseek_base_url: str
    deepseek_api_key: str
    default_model: str
    local_proxy_token: str | None
    model_mapping: dict[str, str]   # 新增
    
    @classmethod
    def load(cls, host: str, port: int) -> "ProxyConfig":
        usage_path = discover_usage_text_path()
        usage_text = read_text_if_exists(usage_path) if usage_path else ""
        settings = read_json_if_exists(SCRIPT_DIR / "proxy_settings.json")
        auth_path = SCRIPT_DIR / "auth.json"

        deepseek_api_key = (
            os.environ.get("DEEPSEEK_API_KEY")
            or settings.get("deepseek_api_key")
            or parse_key_value_from_text(usage_text, "api_key")
            or ""
        )
        default_model = (
            os.environ.get("DEEPSEEK_MODEL")
            or settings.get("default_model")
            or parse_key_value_from_text(usage_text, "default_text_model")
            or "deepseek-v4-pro"
        )
        local_proxy_token = (
            os.environ.get("DEEPSEEK_PROXY_TOKEN")
            or settings.get("local_proxy_token")
            or parse_auth_file(auth_path)
            or DEFAULT_PROXY_AUTH
        )
        deepseek_base_url = (
            os.environ.get("DEEPSEEK_BASE_URL")
            or settings.get("deepseek_base_url")
            or DEFAULT_DEEPSEEK_BASE_URL
        )
        
        model_mapping = settings.get("model_mapping", {})
        if not isinstance(model_mapping, dict):
            model_mapping = {}
        
        return cls(
            host=host,
            port=port,
            deepseek_base_url=str(deepseek_base_url).rstrip("/"),
            deepseek_api_key=deepseek_api_key,
            default_model=default_model,
            local_proxy_token=local_proxy_token,
            model_mapping=model_mapping,   # 新增参数
        )


def emit_sse(handler: BaseHTTPRequestHandler, event_name: str, payload: Any) -> None:
    event_line = f"event: {event_name}\n".encode("utf-8")
    data_line = f"data: {json_dumps(payload)}\n\n".encode("utf-8")
    handler.wfile.write(event_line)
    handler.wfile.write(data_line)
    handler.wfile.flush()


def normalize_content_parts(content: Any) -> list[dict[str, Any]]:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if isinstance(content, list):
        parts: list[dict[str, Any]] = []
        for part in content:
            if isinstance(part, str):
                parts.append({"type": "input_text", "text": part})
            elif isinstance(part, dict):
                parts.append(part)
        return parts
    if isinstance(content, dict):
        return [content]
    return [{"type": "input_text", "text": normalize_to_text(content)}]


def extract_text_from_parts(parts: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for part in parts:
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"}:
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
        elif part_type == "input_image":
            image_url = part.get("image_url") or part.get("file_id") or "image"
            chunks.append(f"[image input: {image_url}]")
        elif "text" in part and isinstance(part.get("text"), str):
            chunks.append(part["text"])
    return "".join(chunks)


def make_chat_tool_call(item: dict[str, Any]) -> dict[str, Any]:
    call_id = item.get("call_id") or item.get("id") or make_id("call")
    raw_name = item.get("name") or item.get("tool_name") or "tool"
    raw_arguments = item.get("arguments") or item.get("input") or "{}"
    if not isinstance(raw_arguments, str):
        raw_arguments = json.dumps(raw_arguments, ensure_ascii=False)
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": raw_name,
            "arguments": raw_arguments,
        },
    }


def convert_response_input_to_messages(
    payload: dict[str, Any],
    reasoning_cache: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    raw_input = payload.get("input", [])
    if isinstance(raw_input, str):
        raw_items: list[Any] = [{"role": "user", "content": raw_input}]
    elif isinstance(raw_input, list):
        raw_items = raw_input
    elif raw_input:
        raw_items = [raw_input]
    else:
        raw_items = []

    messages: list[dict[str, Any]] = []
    pending_tool_calls: list[dict[str, Any]] = []

    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    def flush_pending_tool_calls() -> None:
        if not pending_tool_calls:
            return
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": "",
            "tool_calls": pending_tool_calls.copy(),
        }
        if reasoning_cache:
            for call in pending_tool_calls:
                call_id = call.get("id")
                if isinstance(call_id, str) and call_id in reasoning_cache:
                    assistant_message["reasoning_content"] = reasoning_cache[call_id]
                    break
        messages.append(assistant_message)
        pending_tool_calls.clear()

    for raw_item in raw_items:
        if isinstance(raw_item, str):
            flush_pending_tool_calls()
            messages.append({"role": "user", "content": raw_item})
            continue

        if not isinstance(raw_item, dict):
            flush_pending_tool_calls()
            messages.append({"role": "user", "content": normalize_to_text(raw_item)})
            continue

        item_type = raw_item.get("type")
        role = raw_item.get("role")

        if item_type == "function_call":
            pending_tool_calls.append(make_chat_tool_call(raw_item))
            continue

        if item_type == "function_call_output":
            flush_pending_tool_calls()
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": raw_item.get("call_id") or raw_item.get("id") or "",
                    "content": normalize_to_text(raw_item.get("output")),
                }
            )
            continue

        flush_pending_tool_calls()

        if role:
            normalized_role = "system" if role in {"system", "developer"} else role
            content_parts = normalize_content_parts(raw_item.get("content"))
            text = extract_text_from_parts(content_parts)

            # 提取 reasoning_content（如果存在）
            reasoning_content = raw_item.get("reasoning_content")

            if normalized_role == "assistant" and raw_item.get("tool_calls"):
                msg = {
                    "role": "assistant",
                    "content": text,
                    "tool_calls": raw_item["tool_calls"],
                }
                if reasoning_content:
                    msg["reasoning_content"] = reasoning_content
                messages.append(msg)
                continue

            msg = {"role": normalized_role, "content": text}
            if reasoning_content:
                msg["reasoning_content"] = reasoning_content
            messages.append(msg)
            continue

        if item_type == "message":
            msg_role = raw_item.get("role", "user")
            msg_parts = normalize_content_parts(raw_item.get("content"))
            msg = {
                "role": "system" if msg_role in {"system", "developer"} else msg_role,
                "content": extract_text_from_parts(msg_parts),
            }
            # 如果 message 类型包含 reasoning_content，也要传回去
            reasoning_content = raw_item.get("reasoning_content")
            if reasoning_content:
                msg["reasoning_content"] = reasoning_content
            messages.append(msg)
            continue

        messages.append({"role": "user", "content": normalize_to_text(raw_item)})

    flush_pending_tool_calls()
    return messages


def convert_tools(raw_tools: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_tools, list):
        return []

    converted: list[dict[str, Any]] = []
    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue

        tool_type = tool.get("type")
        if tool_type == "function" and isinstance(tool.get("function"), dict):
            converted.append(tool)
            continue

        if tool_type == "function":
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                continue
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object"}),
                        "strict": bool(tool.get("strict", False)),
                    },
                }
            )
            continue

        # Codex local tools usually arrive as function-style tools. For any
        # other tool type, keep the name/description if available so DeepSeek
        # can still function-call it.
        name = tool.get("name")
        if isinstance(name, str) and name:
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", f"Codex tool: {name}"),
                        "parameters": tool.get("parameters", {"type": "object"}),
                    },
                }
            )

    return converted


def convert_tool_choice(raw_choice: Any) -> Any:
    if raw_choice in {None, "auto", "none", "required"}:
        return raw_choice
    if isinstance(raw_choice, dict):
        if raw_choice.get("type") == "function":
            function_name = raw_choice.get("name")
            if not function_name and isinstance(raw_choice.get("function"), dict):
                function_name = raw_choice["function"].get("name")
            if isinstance(function_name, str) and function_name:
                return {
                    "type": "function",
                    "function": {
                        "name": function_name,
                    },
                }
    return "auto"


def apply_tool_choice_hint(
    messages: list[dict[str, Any]], tool_choice: Any
) -> tuple[list[dict[str, Any]], Any]:
    if tool_choice == "required":
        hint = {
            "role": "system",
            "content": (
                "A tool call is required in the next assistant turn. "
                "Do not answer directly without calling one of the available tools."
            ),
        }
        return [hint, *messages], None

    if isinstance(tool_choice, dict):
        function_name = None
        function_obj = tool_choice.get("function")
        if isinstance(function_obj, dict):
            function_name = function_obj.get("name")
        if isinstance(function_name, str) and function_name:
            hint = {
                "role": "system",
                "content": (
                    f"You must call the function '{function_name}' in the next assistant turn. "
                    "Do not answer directly before making that function call."
                ),
            }
            return [hint, *messages], None

    return messages, tool_choice


def build_deepseek_payload(
    payload: dict[str, Any],
    config: ProxyConfig,
    reasoning_cache: dict[str, str] | None = None,
) -> dict[str, Any]:
    requested_model = payload.get("model")
    model = config.model_mapping.get(requested_model, config.default_model)
    messages = convert_response_input_to_messages(payload, reasoning_cache=reasoning_cache)
    tools = convert_tools(payload.get("tools"))
    tool_choice = convert_tool_choice(payload.get("tool_choice"))
    messages, safe_tool_choice = apply_tool_choice_hint(messages, tool_choice)

    deepseek_payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    if tools:
        deepseek_payload["tools"] = tools
    if safe_tool_choice:
        deepseek_payload["tool_choice"] = safe_tool_choice

    for source_key, target_key in (
        ("temperature", "temperature"),
        ("top_p", "top_p"),
        ("presence_penalty", "presence_penalty"),
        ("frequency_penalty", "frequency_penalty"),
        ("parallel_tool_calls", "parallel_tool_calls"),
        ("max_output_tokens", "max_tokens"),
    ):
        value = payload.get(source_key)
        if value is not None:
            deepseek_payload[target_key] = value

    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if isinstance(effort, str) and effort:
            deepseek_payload["reasoning_effort"] = effort
            deepseek_payload["thinking"] = {"type": "enabled"}

    return deepseek_payload


def map_usage(chat_usage: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(chat_usage, dict):
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "output_tokens_details": {"reasoning_tokens": 0},
        }

    completion_details = chat_usage.get("completion_tokens_details")
    reasoning_tokens = 0
    if isinstance(completion_details, dict):
        maybe_reasoning = completion_details.get("reasoning_tokens")
        if isinstance(maybe_reasoning, int):
            reasoning_tokens = maybe_reasoning

    return {
        "input_tokens": int(chat_usage.get("prompt_tokens", 0) or 0),
        "output_tokens": int(chat_usage.get("completion_tokens", 0) or 0),
        "total_tokens": int(chat_usage.get("total_tokens", 0) or 0),
        "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
    }


def build_response_output_items(
    chat_response: dict[str, Any]
) -> tuple[list[dict[str, Any]], str]:
    choices = chat_response.get("choices")
    if not isinstance(choices, list) or not choices:
        return [], ""

    first_choice = choices[0] or {}
    message = first_choice.get("message") or {}
    text = message.get("content") or ""
    output_items: list[dict[str, Any]] = []

    if isinstance(text, str) and text:
        output_items.append(
            {
                "id": make_id("msg"),
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [],
                    }
                ],
            }
        )

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            function_info = tool_call.get("function") or {}
            arguments = function_info.get("arguments") or ""
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            else:
                parsed_arguments = maybe_parse_json_string(arguments)
                parsed_arguments = decode_nested_json_strings(parsed_arguments)
                if isinstance(parsed_arguments, (dict, list)):
                    arguments = json.dumps(parsed_arguments, ensure_ascii=False)
            output_items.append(
                {
                    "id": make_id("fc"),
                    "type": "function_call",
                    "call_id": tool_call.get("id") or make_id("call"),
                    "name": function_info.get("name") or "tool",
                    "arguments": arguments,
                    "status": "completed",
                }
            )

    return output_items, text if isinstance(text, str) else ""


def cache_reasoning_content(reasoning_cache: dict[str, str], chat_response: dict[str, Any]) -> None:
    choices = chat_response.get("choices")
    if not isinstance(choices, list) or not choices:
        return

    first_choice = choices[0] or {}
    message = first_choice.get("message") or {}
    reasoning_content = message.get("reasoning_content")
    tool_calls = message.get("tool_calls")

    if not isinstance(reasoning_content, str) or not reasoning_content.strip():
        return
    if not isinstance(tool_calls, list):
        return

    for tool_call in tool_calls:
        call_id = tool_call.get("id")
        if isinstance(call_id, str) and call_id:
            reasoning_cache[call_id] = reasoning_content


def build_responses_api_response(
    request_payload: dict[str, Any],
    chat_response: dict[str, Any],
) -> dict[str, Any]:
    output_items, output_text = build_response_output_items(chat_response)
    response_id = make_id("resp")
    reasoning = request_payload.get("reasoning") if isinstance(request_payload.get("reasoning"), dict) else {}
    text_config = request_payload.get("text") if isinstance(request_payload.get("text"), dict) else None
    temperature = request_payload.get("temperature")
    top_p = request_payload.get("top_p")
    max_output_tokens = request_payload.get("max_output_tokens")
    created_at = now_ts()

    return {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "completed_at": created_at,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": request_payload.get("instructions"),
        "max_output_tokens": max_output_tokens,
        "model": chat_response.get("model") or request_payload.get("model"),
        "output": output_items,
        "output_text": output_text,
        "parallel_tool_calls": bool(request_payload.get("parallel_tool_calls", False)),
        "previous_response_id": request_payload.get("previous_response_id"),
        "reasoning": {
            "effort": reasoning.get("effort"),
            "summary": reasoning.get("summary"),
        },
        "store": bool(request_payload.get("store", False)),
        "temperature": request_payload.get("temperature"),
        "text": text_config or {"format": {"type": "text"}},
        "tool_choice": request_payload.get("tool_choice", "auto"),
        "tools": request_payload.get("tools", []),
        "top_p": top_p,
        "truncation": request_payload.get("truncation", "disabled"),
        "usage": map_usage(chat_response.get("usage")),
        "user": request_payload.get("user"),
        "metadata": request_payload.get("metadata", {}),
    }


def invoke_deepseek(config: ProxyConfig, payload: dict[str, Any]) -> dict[str, Any]:
    if not config.deepseek_api_key:
        raise RuntimeError(
            "DeepSeek API key not found. Check the local usage txt file or DEEPSEEK_API_KEY."
        )

    upstream_url = f"{config.deepseek_base_url}/chat/completions"
    upstream_body = json_dumps(payload).encode("utf-8")
    req = request.Request(
        upstream_url,
        method="POST",
        data=upstream_body,
        headers={
            "Authorization": f"Bearer {config.deepseek_api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "codex-deepseek-proxy/1.0",
        },
    )

    try:
        with request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek upstream error {exc.code}: {body}") from exc


class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "DeepSeekCodexProxy/1.0"

    @property
    def config(self) -> ProxyConfig:
        return self.server.proxy_config  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write(
            "[%s] %s - %s\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), self.address_string(), format % args)
        )
        sys.stdout.flush()

    def _write_json(self, status_code: int, payload: Any) -> None:
        body = json_dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _require_auth(self) -> bool:
        required_token = self.config.local_proxy_token
        if not required_token:
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header == f"Bearer {required_token}":
            return True
        self._write_json(
            HTTPStatus.UNAUTHORIZED,
            {
                "error": {
                    "message": "Proxy auth failed. Check whether auth.json OPENAI_API_KEY matches the proxy token.",
                    "type": "invalid_request_error",
                }
            },
        )
        return False

    def do_GET(self) -> None:
        if self.path in {"/health", "/healthz"}:
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "listen": f"http://{self.config.host}:{self.config.port}",
                    "deepseek_base_url": self.config.deepseek_base_url,
                    "default_model": self.config.default_model,
                },
            )
            return

        if self.path == "/v1/models":
            self._write_json(
                HTTPStatus.OK,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.config.default_model,
                            "object": "model",
                            "created": 0,
                            "owned_by": "deepseek-proxy",
                        }
                    ],
                },
            )
            return

        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"error": {"message": f"GET path not implemented: {self.path}"}},
        )

    def do_POST(self) -> None:
        if not self._require_auth():
            return

        try:
            payload = self._read_json_body()
        except json.JSONDecodeError as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"error": {"message": f"JSON parse failed: {exc}"}},
            )
            return

        try:
            if self.path == "/v1/responses":
                self.handle_responses(payload)
                return
            if self.path == "/v1/chat/completions":
                deepseek_payload = build_deepseek_payload(
                    payload,
                    self.config,
                    reasoning_cache=self.server.reasoning_cache,  # type: ignore[attr-defined]
                )
                upstream = invoke_deepseek(self.config, deepseek_payload)
                cache_reasoning_content(self.server.reasoning_cache, upstream)  # type: ignore[attr-defined]
                self._write_json(HTTPStatus.OK, upstream)
                return

            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"message": f"POST path not implemented: {self.path}"}},
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": {
                        "message": str(exc),
                        "type": exc.__class__.__name__,
                    }
                },
            )

    def handle_responses(self, payload: dict[str, Any]) -> None:
        deepseek_payload = build_deepseek_payload(
            payload,
            self.config,
            reasoning_cache=self.server.reasoning_cache,  # type: ignore[attr-defined]
        )
        upstream = invoke_deepseek(self.config, deepseek_payload)
        cache_reasoning_content(self.server.reasoning_cache, upstream)  # type: ignore[attr-defined]
        response_payload = build_responses_api_response(payload, upstream)

        if payload.get("stream"):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.stream_response_events(response_payload)
            self.close_connection = True
            return

        self._write_json(HTTPStatus.OK, response_payload)

    def stream_response_events(self, response_payload: dict[str, Any]) -> None:
        sequence_number = 0

        def emit_typed(event_type: str, **fields: Any) -> None:
            nonlocal sequence_number
            sequence_number += 1
            payload = {"type": event_type, **fields, "sequence_number": sequence_number}
            emit_sse(self, event_type, payload)

        progress_response = self._build_progress_response(response_payload)
        emit_typed("response.created", response=progress_response)
        emit_typed("response.in_progress", response=progress_response)

        output_items = response_payload.get("output", [])
        if not isinstance(output_items, list):
            output_items = []

        for output_index, item in enumerate(output_items):
            item_type = item.get("type")
            if item_type == "message":
                self._stream_message_item(output_index, item, emit_typed)
            elif item_type == "function_call":
                self._stream_function_call_item(output_index, item, emit_typed)
            else:
                emit_typed(
                    "response.output_item.done",
                    output_index=output_index,
                    item=item,
                )

        emit_typed("response.completed", response=response_payload)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True

    def _build_progress_response(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        progress = dict(response_payload)
        progress["status"] = "in_progress"
        progress["completed_at"] = None
        progress["output"] = []
        progress["usage"] = None
        return progress

    def _stream_message_item(
        self,
        output_index: int,
        item: dict[str, Any],
        emit_typed: Any,
    ) -> None:
        content = item.get("content") or []
        text = ""
        if isinstance(content, list) and content:
            first_content = content[0]
            if isinstance(first_content, dict):
                text = first_content.get("text") or ""

        added_item = {
            "id": item.get("id"),
            "type": "message",
            "role": "assistant",
            "status": "in_progress",
            "content": [],
        }
        emit_typed("response.output_item.added", output_index=output_index, item=added_item)
        part = {"type": "output_text", "text": "", "annotations": []}
        emit_typed(
            "response.content_part.added",
            item_id=item.get("id"),
            output_index=output_index,
            content_index=0,
            part=part,
        )
        emit_typed(
            "response.output_text.delta",
            item_id=item.get("id"),
            output_index=output_index,
            content_index=0,
            delta=text,
        )
        emit_typed(
            "response.output_text.done",
            item_id=item.get("id"),
            output_index=output_index,
            content_index=0,
            text=text,
        )
        emit_typed(
            "response.content_part.done",
            item_id=item.get("id"),
            output_index=output_index,
            content_index=0,
            part={"type": "output_text", "text": text, "annotations": []},
        )
        emit_typed("response.output_item.done", output_index=output_index, item=item)

    def _stream_function_call_item(
        self,
        output_index: int,
        item: dict[str, Any],
        emit_typed: Any,
    ) -> None:
        arguments = item.get("arguments") or ""
        added_item = {
            "id": item.get("id"),
            "type": "function_call",
            "call_id": item.get("call_id"),
            "name": item.get("name"),
            "arguments": "",
            "status": "in_progress",
        }
        emit_typed("response.output_item.added", output_index=output_index, item=added_item)
        emit_typed(
            "response.function_call_arguments.delta",
            item_id=item.get("id"),
            output_index=output_index,
            delta=arguments,
        )
        emit_typed(
            "response.function_call_arguments.done",
            item_id=item.get("id"),
            output_index=output_index,
            arguments=arguments,
            name=item.get("name"),
        )
        emit_typed("response.output_item.done", output_index=output_index, item=item)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local proxy from Codex to DeepSeek")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Listen host, default {DEFAULT_HOST}")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Listen port, default {DEFAULT_PORT}"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ProxyConfig.load(host=args.host, port=args.port)

    if not config.deepseek_api_key:
        print("Warning: DeepSeek API key not found. Upstream calls will fail.", file=sys.stderr)

    server = ThreadingHTTPServer((config.host, config.port), ProxyHandler)
    server.proxy_config = config  # type: ignore[attr-defined]
    server.reasoning_cache = {}  # type: ignore[attr-defined]

    print(
        f"DeepSeek proxy started: http://{config.host}:{config.port}\n"
        f"Default model: {config.default_model}\n"
        f"Upstream base URL: {config.deepseek_base_url}\n"
        f"Local auth: {'enabled' if config.local_proxy_token else 'disabled'}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown signal received. Proxy stopped.", flush=True)


if __name__ == "__main__":
    main()
