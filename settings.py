"""Validated plugin settings with conservative bounds."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

CONFIG_SECTIONS: dict[str, tuple[str, ...]] = {
    "basic_settings": ("enabled", "private_enabled", "group_enabled"),
    "judgement_settings": (
        "judge_provider_id",
        "confidence_threshold",
        "judge_timeout_seconds",
    ),
    "context_settings": ("history_limit", "session_ttl_minutes"),
    "advanced_settings": (
        "max_message_chars",
        "max_context_chars",
        "judge_max_tokens",
        "debug_log",
    ),
}
CONFIG_LAYOUT_VERSION_KEY = "config_layout_version"
CURRENT_CONFIG_LAYOUT_VERSION = 2

_MISSING = object()


def _uses_legacy_layout(config: Mapping[str, Any]) -> bool:
    version = config.get(CONFIG_LAYOUT_VERSION_KEY, 1)
    return (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < CURRENT_CONFIG_LAYOUT_VERSION
    )


def _setting_value(
    config: Mapping[str, Any],
    section: str,
    key: str,
    default: Any,
) -> Any:
    """Read new grouped settings while retaining legacy flat-config support."""

    if _uses_legacy_layout(config):
        legacy_value = config.get(key, _MISSING)
        if legacy_value is not _MISSING:
            return legacy_value
    section_value = config.get(section, {})
    if not isinstance(section_value, Mapping):
        return default
    return section_value.get(key, default)


def migrate_legacy_config(config: MutableMapping[str, Any]) -> bool:
    """Move legacy flat keys into the grouped schema without losing values."""

    if not _uses_legacy_layout(config):
        return False

    for section, keys in CONFIG_SECTIONS.items():
        legacy_values = {key: config[key] for key in keys if key in config}
        if not legacy_values:
            continue
        current = config.get(section, {})
        grouped = dict(current) if isinstance(current, Mapping) else {}
        grouped.update(legacy_values)
        config[section] = grouped
    config[CONFIG_LAYOUT_VERSION_KEY] = CURRENT_CONFIG_LAYOUT_VERSION
    return True


def _bool_value(
    config: Mapping[str, Any],
    section: str,
    key: str,
    default: bool,
) -> bool:
    value = _setting_value(config, section, key, default)
    return value if isinstance(value, bool) else default


def _number_value(
    config: Mapping[str, Any],
    section: str,
    key: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    value = _setting_value(config, section, key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return min(max(float(value), minimum), maximum)


def _int_value(
    config: Mapping[str, Any],
    section: str,
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = _setting_value(config, section, key, default)
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

        provider = _setting_value(
            config,
            "judgement_settings",
            "judge_provider_id",
            "",
        )
        provider_id = provider.strip() if isinstance(provider, str) else ""
        return cls(
            enabled=_bool_value(config, "basic_settings", "enabled", True),
            private_enabled=_bool_value(
                config,
                "basic_settings",
                "private_enabled",
                True,
            ),
            group_enabled=_bool_value(
                config,
                "basic_settings",
                "group_enabled",
                False,
            ),
            judge_provider_id=provider_id,
            history_limit=_int_value(
                config,
                "context_settings",
                "history_limit",
                10,
                4,
                30,
            ),
            confidence_threshold=_number_value(
                config,
                "judgement_settings",
                "confidence_threshold",
                0.85,
                0.5,
                1.0,
            ),
            judge_timeout_seconds=_number_value(
                config,
                "judgement_settings",
                "judge_timeout_seconds",
                5.0,
                1.0,
                30.0,
            ),
            debug_log=_bool_value(
                config,
                "advanced_settings",
                "debug_log",
                False,
            ),
            session_ttl_minutes=_int_value(
                config,
                "context_settings",
                "session_ttl_minutes",
                1440,
                5,
                10080,
            ),
            max_message_chars=_int_value(
                config,
                "advanced_settings",
                "max_message_chars",
                800,
                100,
                4000,
            ),
            max_context_chars=_int_value(
                config,
                "advanced_settings",
                "max_context_chars",
                6000,
                1000,
                20000,
            ),
            judge_max_tokens=_int_value(
                config,
                "advanced_settings",
                "judge_max_tokens",
                160,
                64,
                512,
            ),
        )
