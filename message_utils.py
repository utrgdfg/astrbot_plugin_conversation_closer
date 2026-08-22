"""Small adapters for bounded text and AstrBot message chains."""

from __future__ import annotations

from collections.abc import Iterable

MEDIA_PLACEHOLDERS = {
    "image": "[图片]",
    "record": "[语音]",
    "video": "[视频]",
    "file": "[文件]",
}
TRUNCATION_MARKER = "[内容截断]"
UNKNOWN_MESSAGE_PLACEHOLDER = "[其他消息]"
REPLY_MESSAGE_PLACEHOLDER = "[引用消息]"
LOSSY_CONTEXT_MARKERS = frozenset(
    {
        *MEDIA_PLACEHOLDERS.values(),
        REPLY_MESSAGE_PLACEHOLDER,
        UNKNOWN_MESSAGE_PLACEHOLDER,
    }
)
STRUCTURAL_COMPONENTS = frozenset({"at", "atall"})


def bound_text(content: str, limit: int) -> str:
    """Bound stored text while retaining both beginning and end."""

    normalized = content.strip()
    if len(normalized) <= limit:
        return normalized
    head = limit // 2 - 5
    tail = limit - head - 10
    return f"{normalized[:head]}{TRUNCATION_MARKER}{normalized[-tail:]}"


def extract_message_chain(chain: Iterable[object] | None) -> str:
    """Extract plain text and lightweight placeholders without binary data."""

    if chain is None:
        return ""
    parts: list[str] = []
    for component in chain:
        kind = type(component).__name__.lower()
        if kind == "plain":
            text = getattr(component, "text", "")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
            continue
        if kind == "record":
            text = getattr(component, "text", "")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
            parts.append(MEDIA_PLACEHOLDERS["record"])
            continue
        if kind == "reply":
            quoted = getattr(component, "message_str", "")
            if isinstance(quoted, str) and quoted.strip():
                parts.append(quoted.strip())
            parts.append(REPLY_MESSAGE_PLACEHOLDER)
            continue
        placeholder = MEDIA_PLACEHOLDERS.get(kind)
        if placeholder is not None:
            parts.append(placeholder)
            continue
        if kind in STRUCTURAL_COMPONENTS:
            continue
        for attribute in ("text", "title", "content"):
            value = getattr(component, attribute, "")
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        parts.append(UNKNOWN_MESSAGE_PLACEHOLDER)
    return "\n".join(parts)
