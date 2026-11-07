from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def slugify_key(text: str) -> str:
    """Convert a free-text field label into a stable snake_case key."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    text = re.sub(r"_+", "_", text)
    if not text:
        return "field"
    if text[0].isdigit():
        text = f"f_{text}"
    return text[:64]


def estimate_tokens(text: str) -> int:
    """Conservative token estimate (~4 chars/token) used only for context budgeting."""
    return max(1, len(text) // 4) if text else 0


def strip_code_fences(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```[a-zA-Z0-9_-]*\s*\n(.*?)\n?```\s*$", t, re.S)
    return m.group(1).strip() if m else t


def extract_json_object(text: str) -> Any:
    """Parse the first complete JSON object in ``text``.

    Raises ``ValueError`` if no valid JSON object can be found. Never repairs or
    fabricates content: a malformed response stays malformed.
    """
    if text is None:
        raise ValueError("empty response")
    t = strip_code_fences(text)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # Find a balanced {...} block, respecting strings.
    start = t.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = t[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = t.find("{", start + 1)
    raise ValueError("no valid JSON object found in response")


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()
