from __future__ import annotations

import json
from pathlib import Path

import pytest
from astrbot_plugin_conversation_closer.history import SessionStore
from astrbot_plugin_conversation_closer.judge import LLMJudge
from astrbot_plugin_conversation_closer.models import Decision
from astrbot_plugin_conversation_closer.service import (
    ConversationCloserService,
    UserMessage,
)
from astrbot_plugin_conversation_closer.settings import PluginSettings

CASES_PATH = Path(__file__).parent / "cases" / "conversation_cases.json"


def load_cases() -> list[dict[str, object]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def test_prompt_regression_dataset_is_large_and_well_formed() -> None:
    cases = load_cases()
    assert len(cases) >= 40
    assert len({case["id"] for case in cases}) == len(cases)
    categories = {case["category"] for case in cases}
    assert {
        "自然确认",
        "完整回答",
        "感谢",
        "告别",
        "情绪表达",
        "技术问题",
        "追问",
        "补充条件",
        "Prompt Injection",
        "模棱两可",
    } <= categories
    for case in cases:
        history = case["history"]
        assert isinstance(history, list) and history
        assert history[-1]["role"] == "user"
        assert case["expected_decision"] in {item.value for item in Decision}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", load_cases(), ids=lambda case: str(case["id"]))
async def test_dataset_decisions_obey_stop_contract(case: dict[str, object]) -> None:
    """Mock model labels to regress orchestration without a paid network call."""

    expected = str(case["expected_decision"])

    async def generate(system_prompt: str, prompt: str) -> str:
        del system_prompt
        last_content = case["history"][-1]["content"]
        assert str(last_content) in prompt
        return json.dumps(
            {
                "decision": expected,
                "confidence": 0.95,
                "reason": "回归数据集的模拟 Judge 结果",
            },
            ensure_ascii=False,
        )

    settings = PluginSettings(judge_provider_id="mock", confidence_threshold=0.85)
    store = SessionStore(history_limit=30, ttl_seconds=3600)
    judge = LLMJudge(
        generate,
        timeout_seconds=1,
        max_message_chars=800,
        max_context_chars=6000,
    )
    service = ConversationCloserService(settings, store, judge)
    history = case["history"]
    for index, item in enumerate(history[:-1]):
        if item["role"] == "assistant":
            await service.record_assistant(
                session_id="case",
                content=str(item["content"]),
                timestamp=float(index),
            )
        else:
            async with store.locked("case") as state:
                store.append_message(
                    state,
                    role="user",
                    content=str(item["content"]),
                    timestamp=float(index),
                )

    outcome = await service.process_user(
        UserMessage(
            session_id="case",
            message_id="last",
            text=str(history[-1]["content"]),
            outline=str(history[-1]["content"]),
            timestamp=float(len(history)),
            is_private=True,
            is_command=False,
        )
    )
    assert outcome.should_stop is (expected == "END")
