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
        placeholder = MEDIA_PLACEHOLDERS.get(kind)
        if placeholder is not None:
            parts.append(placeholder)
    return "\n".join(parts)
