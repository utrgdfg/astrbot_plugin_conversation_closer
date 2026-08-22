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
    assert await store.snapshot("session") == ()


@pytest.mark.asyncio
async def test_reused_message_id_with_different_content_is_not_a_duplicate() -> None:
    calls = 0

    async def generate(system_prompt: str, prompt: str) -> str:
        nonlocal calls
        del system_prompt
        calls += 1
        if "请处理新问题" in prompt:
            return '{"decision":"CONTINUE","confidence":0.99,"reason":"出现新请求"}'
        return '{"decision":"END","confidence":0.99,"reason":"确认已经完成"}'

    settings = PluginSettings(judge_provider_id="judge")
    store = SessionStore(history_limit=10, ttl_seconds=3600)
    judge = LLMJudge(
        generate,
        timeout_seconds=1,
        max_message_chars=800,
        max_context_chars=6000,
    )
    service = ConversationCloserService(settings, store, judge)
    await service.record_assistant(
        session_id="session",
        content="那先这样",
        timestamp=0,
    )

    first = await service.process_user(
        UserMessage("session", "reused", "可以", "可以", 1, True, False)
    )
    second = await service.process_user(
        UserMessage(
            "session",
            "reused",
            "请处理新问题",
            "请处理新问题",
            2,
            True,
            False,
        )
    )

    assert first.should_stop is True
    assert second.should_stop is False
    assert second.duplicate is False
    assert calls == 2
    assert [item.content for item in await store.snapshot("session")] == [
        "请处理新问题",
    ]


@pytest.mark.asyncio
async def test_successful_end_starts_a_fresh_history_epoch() -> None:
    async def generate(system_prompt: str, prompt: str) -> str:
        del system_prompt, prompt
        return '{"decision":"END","confidence":0.99,"reason":"自然闭环"}'

    settings = PluginSettings(judge_provider_id="judge", history_limit=4)
    store = SessionStore(history_limit=4, ttl_seconds=3600)
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

    for index in range(6):
        await service.record_assistant(
            session_id="s",
            content="晚安",
            timestamp=float(index * 2),
        )
        outcome = await service.process_user(
            UserMessage(
                "s",
                str(index),
                "晚安",
                "晚安",
                float(index * 2 + 1),
                True,
                False,
            )
        )
        assert outcome.should_stop is True
        assert await store.snapshot("s") == ()

    async with store.locked("s") as state:
        assert state.dropped_message_count == 0


@pytest.mark.asyncio
async def test_reused_message_id_and_content_with_new_timestamp_is_not_duplicate() -> None:
    calls = 0

    async def generate(system_prompt: str, prompt: str) -> str:
        nonlocal calls
        del system_prompt, prompt
        calls += 1
        return '{"decision":"CONTINUE","confidence":0.99,"reason":"继续"}'

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

    first = await service.process_user(
        UserMessage("session", "reused", "相同文本", "相同文本", 1, True, False)
    )
    second = await service.process_user(
        UserMessage("session", "reused", "相同文本", "相同文本", 2, True, False)
    )

    assert first.duplicate is False
    assert second.duplicate is False
    assert calls == 2


@pytest.mark.asyncio
async def test_duplicate_preserves_original_judged_flag() -> None:
    settings = PluginSettings(judge_provider_id="")
    store = SessionStore(history_limit=10, ttl_seconds=3600)
    judge = LLMJudge(
        lambda *_: None,  # type: ignore[arg-type,return-value]
        timeout_seconds=1,
        max_message_chars=800,
        max_context_chars=6000,
    )
    service = ConversationCloserService(settings, store, judge)
    message = UserMessage("session", "same", "问题", "问题", 1, True, False)

    first = await service.process_user(message)
    second = await service.process_user(message)

    assert first.judged is False
    assert second.judged is False
    assert second.duplicate is True


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
async def test_evicted_history_can_only_downgrade_end() -> None:
    async def generate(system_prompt: str, prompt: str) -> str:
        del system_prompt
        assert '"context_complete":false' in prompt
        assert '"omitted_message_count":1' in prompt
        return '{"decision":"END","confidence":0.99,"reason":"局部回答完成"}'

    settings = PluginSettings(judge_provider_id="judge", history_limit=4)
    store = SessionStore(history_limit=4, ttl_seconds=3600)
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
    async with store.locked("s") as state:
        for role, content, timestamp in (
            ("user", "请帮我修复服务", 0),
            ("assistant", "请提供版本号", 1),
            ("user", "示例版本", 2),
            ("assistant", "请再提供错误码", 3),
        ):
            store.append_message(
                state,
                role=role,
                content=content,
                timestamp=timestamp,
            )

    outcome = await service.process_user(
        UserMessage("s", "last", "E_EXAMPLE", "E_EXAMPLE", 4, True, False)
    )

    assert outcome.should_stop is False
    assert outcome.result is not None
    assert outcome.result.decision is Decision.UNCERTAIN
    assert outcome.result.error_code == "incomplete_context"


@pytest.mark.asyncio
async def test_cancelled_judge_rolls_back_user_history() -> None:
    started = asyncio.Event()

    async def generate(system_prompt: str, prompt: str) -> str:
        del system_prompt, prompt
        started.set()
        await asyncio.Future()
        raise AssertionError("unreachable")

    settings = PluginSettings(judge_provider_id="judge")
    store = SessionStore(history_limit=10, ttl_seconds=3600)
    judge = LLMJudge(
        generate,
        timeout_seconds=30,
        max_message_chars=800,
        max_context_chars=6000,
    )
    service = ConversationCloserService(settings, store, judge)
    await service.record_assistant(session_id="s", content="上一条回复", timestamp=0)
    task = asyncio.create_task(
        service.process_user(
            UserMessage("s", "1", "当前消息", "当前消息", 1, True, False)
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert [item.content for item in await store.snapshot("s")] == ["上一条回复"]
    await judge.close()


@pytest.mark.asyncio
async def test_cancelled_id_collision_preserves_previous_dedup_entry() -> None:
    calls = 0
    collision_started = asyncio.Event()

    async def generate(system_prompt: str, prompt: str) -> str:
        nonlocal calls
        del system_prompt
        calls += 1
        if "冲突消息" in prompt:
            collision_started.set()
            await asyncio.Future()
        return '{"decision":"CONTINUE","confidence":0.99,"reason":"继续"}'

    settings = PluginSettings(judge_provider_id="judge")
    store = SessionStore(history_limit=10, ttl_seconds=3600)
    judge = LLMJudge(
        generate,
        timeout_seconds=30,
        max_message_chars=800,
        max_context_chars=6000,
    )
    service = ConversationCloserService(settings, store, judge)
    original = UserMessage("s", "same", "原消息", "原消息", 1, True, False)
    collision = UserMessage("s", "same", "冲突消息", "冲突消息", 2, True, False)

    first = await service.process_user(original)
    collision_task = asyncio.create_task(service.process_user(collision))
    await collision_started.wait()
    collision_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await collision_task
    repeated = await service.process_user(original)

    assert first.duplicate is False
    assert repeated.duplicate is True
    assert calls == 2
    assert [item.content for item in await store.snapshot("s")] == ["原消息"]
    await judge.close()


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
        store.remember_processed(
            state,
            str(index),
            str(index).encode(),
            result,
            judged=True,
        )
    assert list(state.processed) == ["7", "8", "9"]
