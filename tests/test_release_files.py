from __future__ import annotations

import json
import struct
import tomllib
from pathlib import Path

import yaml
from astrbot_plugin_conversation_closer import __version__
from astrbot_plugin_conversation_closer.settings import (
    CONFIG_LAYOUT_VERSION_KEY,
    CONFIG_SECTIONS,
    PluginSettings,
)

ROOT = Path(__file__).parents[1]


def test_metadata_identity_and_versions_are_release_ready() -> None:
    metadata = yaml.safe_load((ROOT / "metadata.yaml").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["name"] == "astrbot_plugin_conversation_closer"
    assert metadata["author"] == "utrgdfg"
    assert metadata["version"] == __version__ == project["project"]["version"]
    assert metadata["repo"] == (
        "https://github.com/utrgdfg/astrbot_plugin_conversation_closer"
    )
    assert metadata["astrbot_version"] == ">=4.24.2,<5"
    assert metadata["display_name"] == "对话自然收尾"
    assert "support_platforms" not in metadata


def _schema_defaults(schema: dict) -> dict:
    defaults = {}
    for name, definition in schema.items():
        if definition["type"] == "object":
            defaults[name] = _schema_defaults(definition["items"])
        else:
            defaults[name] = definition["default"]
    return defaults


def test_config_schema_defaults_match_runtime_settings() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    defaults = _schema_defaults(schema)
    settings = PluginSettings.from_mapping(defaults)

    visible_sections = [
        name for name, definition in schema.items() if not definition.get("invisible")
    ]
    assert visible_sections == [
        "basic_settings",
        "judgement_settings",
        "context_settings",
        "advanced_settings",
    ]
    legacy_keys = {key for keys in CONFIG_SECTIONS.values() for key in keys}
    assert set(schema) - set(visible_sections) == {
        *legacy_keys,
        CONFIG_LAYOUT_VERSION_KEY,
    }
    defaults = PluginSettings()
    for key in legacy_keys:
        assert schema[key]["default"] == getattr(defaults, key)
        assert schema[key]["invisible"] is True
    assert schema[CONFIG_LAYOUT_VERSION_KEY]["default"] == 1
    assert schema[CONFIG_LAYOUT_VERSION_KEY]["invisible"] is True
    provider = schema["judgement_settings"]["items"]["judge_provider_id"]
    assert provider["description"] == "对话判断模型"
    assert provider["_special"] == "select_provider"
    assert settings == PluginSettings()


def test_user_facing_i18n_and_readme_layout() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    visible_sections = [
        name for name, definition in schema.items() if not definition.get("invisible")
    ]
    for locale in ("zh-CN", "en-US"):
        translations = json.loads(
            (ROOT / ".astrbot-plugin" / "i18n" / f"{locale}.json").read_text(
                encoding="utf-8"
            )
        )
        assert translations["metadata"]["display_name"] == "对话自然收尾"
        if locale == "en-US":
            assert list(translations["config"]) == visible_sections

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    counter = (
        "[![萌娘计数器]"
        "(https://mayu.due.moe/get/"
        "@utrgdfg-astrbot_plugin_conversation_closer?theme=booru-lewd)]"
        "(https://github.com/utrgdfg/astrbot_plugin_conversation_closer)"
    )
    assert readme.startswith("# 对话自然收尾\n")
    assert readme.rstrip().endswith(counter)
    assert "`logo.png`" not in readme

    chinese_headings = {
        "CHANGELOG.md": "# 更新日志\n",
        "CONTRIBUTING.md": "# 参与贡献\n",
        "SECURITY.md": "# 安全策略\n",
        "ASSET_LICENSE.md": "# 资源授权说明\n",
        "docs/RELEASE_CHECKLIST.md": "# 发布检查清单\n",
        "tests/cases/README.md": "# 对话判断测试语料\n",
    }
    for relative_path, heading in chinese_headings.items():
        assert (ROOT / relative_path).read_text(encoding="utf-8").startswith(heading)

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["description"] == (
        "使用独立模型判断 AstrBot 对话是否已经自然结束。"
    )
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.startswith("name: 持续集成\n")
    assert "Check out repository" not in workflow


def test_logo_is_exactly_256_square_png() -> None:
    data = (ROOT / "logo.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (256, 256)


def test_production_code_has_no_random_or_direct_network_implementation() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ROOT.glob("*.py")
        if path.name != "__init__.py"
    )
    assert "import random" not in source
    assert "from random" not in source
    assert "requests." not in source
    assert "aiohttp." not in source
    assert "httpx." not in source
    assert "subprocess" not in source
    assert "eval(" not in source
    assert "exec(" not in source
