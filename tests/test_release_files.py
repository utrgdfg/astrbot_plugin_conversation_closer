from __future__ import annotations

import json
import struct
import tomllib
from pathlib import Path

import yaml
from astrbot_plugin_conversation_closer import __version__
from astrbot_plugin_conversation_closer.settings import PluginSettings

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
    assert "support_platforms" not in metadata


def test_config_schema_defaults_match_runtime_settings() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    defaults = {name: definition["default"] for name, definition in schema.items()}
    settings = PluginSettings.from_mapping(defaults)

    assert len(schema) == 12
    assert schema["judge_provider_id"]["_special"] == "select_provider"
    assert settings == PluginSettings()


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
