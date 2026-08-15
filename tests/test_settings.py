from __future__ import annotations

from astrbot_plugin_conversation_closer.settings import (
    CURRENT_CONFIG_LAYOUT_VERSION,
    PluginSettings,
    migrate_legacy_config,
)


def test_grouped_config_loads_user_values() -> None:
    settings = PluginSettings.from_mapping(
        {
            "basic_settings": {
                "enabled": False,
                "private_enabled": False,
                "group_enabled": True,
            },
            "judgement_settings": {
                "judge_provider_id": " small-model ",
                "confidence_threshold": 0.92,
                "judge_timeout_seconds": 3.5,
            },
            "context_settings": {
                "history_limit": 14,
                "session_ttl_minutes": 120,
            },
            "advanced_settings": {
                "max_message_chars": 900,
                "max_context_chars": 7000,
                "judge_max_tokens": 192,
                "debug_log": True,
            },
        }
    )

    assert settings == PluginSettings(
        enabled=False,
        private_enabled=False,
        group_enabled=True,
        judge_provider_id="small-model",
        history_limit=14,
        confidence_threshold=0.92,
        judge_timeout_seconds=3.5,
        debug_log=True,
        session_ttl_minutes=120,
        max_message_chars=900,
        max_context_chars=7000,
        judge_max_tokens=192,
    )


def test_legacy_config_migration_preserves_values_and_is_idempotent() -> None:
    config = {
        "enabled": False,
        "judge_provider_id": "legacy-model",
        "history_limit": 18,
        "debug_log": True,
        "basic_settings": {"enabled": True, "private_enabled": True},
        "judgement_settings": {"judge_provider_id": "default-model"},
    }

    assert migrate_legacy_config(config) is True
    assert migrate_legacy_config(config) is False
    legacy_keys = {
        "enabled",
        "judge_provider_id",
        "history_limit",
        "debug_log",
    }
    assert all(config[key] is not None for key in legacy_keys)
    assert config["config_layout_version"] == CURRENT_CONFIG_LAYOUT_VERSION
    assert config["basic_settings"]["enabled"] is False
    assert config["basic_settings"]["private_enabled"] is True
    assert config["judgement_settings"]["judge_provider_id"] == "legacy-model"
    assert config["context_settings"]["history_limit"] == 18
    assert config["advanced_settings"]["debug_log"] is True

    settings = PluginSettings.from_mapping(config)
    assert settings.enabled is False
    assert settings.private_enabled is True
    assert settings.judge_provider_id == "legacy-model"
    assert settings.history_limit == 18
    assert settings.debug_log is True


def test_legacy_flat_values_remain_readable_without_mutation() -> None:
    settings = PluginSettings.from_mapping(
        {
            "enabled": False,
            "judge_provider_id": "legacy-model",
            "history_limit": 8,
            "confidence_threshold": 0.9,
        }
    )

    assert settings.enabled is False
    assert settings.judge_provider_id == "legacy-model"
    assert settings.history_limit == 8
    assert settings.confidence_threshold == 0.9


def test_current_layout_ignores_stale_hidden_legacy_values() -> None:
    config = {
        "config_layout_version": CURRENT_CONFIG_LAYOUT_VERSION,
        "enabled": False,
        "judge_provider_id": "stale-model",
        "history_limit": 4,
        "basic_settings": {
            "enabled": True,
            "private_enabled": True,
            "group_enabled": False,
        },
        "judgement_settings": {
            "judge_provider_id": "current-model",
            "confidence_threshold": 0.9,
            "judge_timeout_seconds": 5.0,
        },
        "context_settings": {
            "history_limit": 16,
            "session_ttl_minutes": 1440,
        },
    }

    assert migrate_legacy_config(config) is False
    settings = PluginSettings.from_mapping(config)
    assert settings.enabled is True
    assert settings.judge_provider_id == "current-model"
    assert settings.history_limit == 16
