from __future__ import annotations

import asyncio

import pytest
from astrbot_plugin_conversation_closer.history import SessionStore
from astrbot_plugin_conversation_closer.judge import LLMJudge
from astrbot_plugin_conversation_closer.models import Decision, JudgeResult
from astrbot_plugin_conversation_closer.service import (
    ConversationCloserService,
    UserMessage,
)
from astrbot_plugin_conversation_closer.settings import PluginSettings


@pytest.mark.asyncio
async def test_history_is_bounded_and_sessions_are_isolated() -> None:
    store = SessionStore(history_limit=4, ttl_seconds=3600)
    for index in range(6):
        await store.record_assistant("session-a", f"a-{index}", index)
    await store.record_assistant("session-b", "b-only", 1)

    first = await store.snapshot("session-a")
    second = await store.snapshot("session-b")
    assert [item.content for item in first] == ["a-2", "a-3", "a-4", "a-5"]
    assert [item.content for item in second] == ["b-only"]


@pytest.mark.asyncio
async def test_message_id_deduplicates_history_and_judge() -> None:
    calls = 0

    async def generate(system_prompt: str, prompt: str) -> str:
        nonlocal calls
        del system_prompt, prompt
        calls += 1
        return '{"decision":"END","confidence":0.95,"reason":"已完成确认"}'

    settings = PluginSettings(judge_provider_id="judge")
    store = SessionStore(history_limit=10, ttl_seconds=3600)
    service = ConversationCloserService(
        settings,
        store,
        LLMJudge(
            generate,
            timeout_seconds=1,
            max_message_chars=800,
            max_context_chars=6000,
        ),
    )
    await service.record_assistant(
        session_id="session",
        content="出去买点吃的吧",
        timestamp=0,
    )
    incoming = UserMessage("session", "same-id", "可以", "可以", 1, True, False)
    first, second = await asyncio.gather(
        service.process_user(incoming),
        service.process_user(incoming),
    )

    assert calls == 1
    assert first.should_stop is True
    assert second.should_stop is True
    assert {first.duplicate, second.duplicate} == {False, True}
    assert len(await store.snapshot("session")) == 2


@pytest.mark.asyncio
async def test_same_session_concurrency_preserves_order() -> None:
    seen_latest: list[str] = []

    async def generate(system_prompt: str, prompt: str) -> str:
        del system_prompt
        if "first" in prompt and "second" not in prompt:
            await asyncio.sleep(0.02)
        seen_latest.append(prompt)
        return '{"decision":"CONTINUE","confidence":0.99,"reason":"仍需继续"}'

    settings = PluginSettings(judge_provider_id="judge")
    store = SessionStore(history_limit=10, ttl_seconds=3600)
    service = ConversationCloserService(
        settings,
        store,
        LLMJudge(
            generate,
            timeout_seconds=1,
            max_message_chars=800,
            max_context_chars=6000,
        ),
    )
    await asyncio.gather(
        service.process_user(UserMessage("s", "1", "first", "first", 1, True, False)),
        service.process_user(UserMessage("s", "2", "second", "second", 2, True, False)),
    )

    history = await store.snapshot("s")
    assert [item.content for item in history] == ["first", "second"]
    assert len(seen_latest) == 2
    assert "first" in seen_latest[0]
    assert "first" in seen_latest[1] and "second" in seen_latest[1]


@pytest.mark.asyncio
async def test_stored_content_truncation_can_only_downgrade_end() -> None:
    async def generate(system_prompt: str, prompt: str) -> str:
        del system_prompt
        assert '"context_complete":false' in prompt
        return '{"decision":"END","confidence":0.99,"reason":"看似完成"}'

    settings = PluginSettings(judge_provider_id="judge", max_message_chars=40)
    store = SessionStore(history_limit=10, ttl_seconds=3600)
    service = ConversationCloserService(
        settings,
        store,
        LLMJudge(
            generate,
            timeout_seconds=1,
            max_message_chars=40,
            max_context_chars=6000,
        ),
    )
    await service.record_assistant(
        session_id="s",
        content="为了继续完成原始任务，请先提供必要信息。" * 10,
        timestamp=0,
    )
    outcome = await service.process_user(
        UserMessage("s", "1", "已经提供", "已经提供", 1, True, False)
    )
    assert outcome.should_stop is False
    assert outcome.result is not None
    assert outcome.result.decision is Decision.UNCERTAIN
    assert outcome.result.error_code == "incomplete_context"


@pytest.mark.asyncio
async def test_stale_session_cleanup_skips_active_lock() -> None:
    now = 0.0

    def clock() -> float:
        return now

    store = SessionStore(history_limit=10, ttl_seconds=10, clock=clock)
    state = store._get_or_create("old")  # noqa: SLF001 - focused store invariant test
    async with state.lock:
        now = 20.0
        assert store.cleanup_stale(force=True) == 0
    assert store.cleanup_stale(force=True) == 1
    assert store.session_count == 0
    assert state.history.maxlen == 10


@pytest.mark.asyncio
async def test_clear_and_close_release_cache() -> None:
    store = SessionStore(history_limit=10, ttl_seconds=3600)
    await store.record_assistant("s", "reply", 1)
    assert await store.clear("s") == 1
    assert await store.snapshot("s") == ()
    await store.close()
    await store.close()
    assert store.session_count == 0


def test_processed_cache_is_bounded() -> None:
    store = SessionStore(history_limit=4, ttl_seconds=3600, message_cache_limit=3)
    state = store._get_or_create("s")  # noqa: SLF001 - focused cache invariant test
    result = JudgeResult(Decision.CONTINUE, 1.0, "continue")
    for index in range(10):
        store.remember_processed(state, str(index), result)
    assert list(state.processed) == ["7", "8", "9"]
