"""Validated plugin settings with conservative bounds."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _bool_value(config: Mapping[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    return value if isinstance(value, bool) else default


def _number_value(
    config: Mapping[str, Any],
    key: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return min(max(float(value), minimum), maximum)


def _int_value(
    config: Mapping[str, Any],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(max(value, minimum), maximum)


@dataclass(frozen=True, slots=True)
class PluginSettings:
    """Runtime settings derived from ``AstrBotConfig``."""

    enabled: bool = True
    private_enabled: bool = True
    group_enabled: bool = False
    judge_provider_id: str = ""
    history_limit: int = 10
    confidence_threshold: float = 0.85
    judge_timeout_seconds: float = 5.0
    debug_log: bool = False
    session_ttl_minutes: int = 1440
    max_message_chars: int = 800
    max_context_chars: int = 6000
    judge_max_tokens: int = 160

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> PluginSettings:
        """Load known settings and clamp resource-related values."""

        provider = config.get("judge_provider_id", "")
        provider_id = provider.strip() if isinstance(provider, str) else ""
        return cls(
            enabled=_bool_value(config, "enabled", True),
            private_enabled=_bool_value(config, "private_enabled", True),
            group_enabled=_bool_value(config, "group_enabled", False),
            judge_provider_id=provider_id,
            history_limit=_int_value(config, "history_limit", 10, 4, 30),
            confidence_threshold=_number_value(
                config,
                "confidence_threshold",
                0.85,
                0.5,
                1.0,
            ),
            judge_timeout_seconds=_number_value(
                config,
                "judge_timeout_seconds",
                5.0,
                1.0,
                30.0,
            ),
            debug_log=_bool_value(config, "debug_log", False),
            session_ttl_minutes=_int_value(
                config,
                "session_ttl_minutes",
                1440,
                5,
                10080,
            ),
            max_message_chars=_int_value(
                config,
                "max_message_chars",
                800,
                100,
                4000,
            ),
            max_context_chars=_int_value(
                config,
                "max_context_chars",
                6000,
                1000,
                20000,
            ),
            judge_max_tokens=_int_value(
                config,
                "judge_max_tokens",
                160,
                64,
                512,
            ),
        )
