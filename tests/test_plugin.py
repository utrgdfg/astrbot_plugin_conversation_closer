from __future__ import annotations

import logging
import sys
import types
from dataclasses import dataclass

import pytest


class _FilterStub:
    class EventMessageType:
        ALL = "all"

    @staticmethod
    def event_message_type(*args, **kwargs):
        del args, kwargs

        def decorator(func):
            return func

        return decorator

    @staticmethod
    def after_message_sent(*args, **kwargs):
        del args, kwargs

        def decorator(func):
            return func

        return decorator

    @staticmethod
    def on_decorating_result(*args, **kwargs):
        del args, kwargs

        def decorator(func):
            return func

        return decorator

    @staticmethod
    def command_group(*args, **kwargs):
        del args, kwargs

        def decorator(func):
            def command(*command_args, **command_kwargs):
                del command_args, command_kwargs

                def command_decorator(command_func):
                    return command_func

                return command_decorator

            func.command = command
            return func

        return decorator


class _StarStub:
    def __init__(self, context) -> None:
        self.context = context


astrbot_module = types.ModuleType("astrbot")
api_module = types.ModuleType("astrbot.api")
event_module = types.ModuleType("astrbot.api.event")
star_module = types.ModuleType("astrbot.api.star")
api_module.AstrBotConfig = dict
api_module.logger = logging.getLogger("astrbot-test")
event_module.AstrMessageEvent = object
event_module.filter = _FilterStub
star_module.Context = object
star_module.Star = _StarStub
sys.modules.setdefault("astrbot", astrbot_module)
sys.modules.setdefault("astrbot.api", api_module)
sys.modules.setdefault("astrbot.api.event", event_module)
sys.modules.setdefault("astrbot.api.star", star_module)

from astrbot_plugin_conversation_closer.main import ConversationCloserPlugin  # noqa: E402
from astrbot_plugin_conversation_closer.models import Decision, JudgeResult  # noqa: E402


class Plain:
    def __init__(self, text: str) -> None:
        self.text = text


class Image:
    pass


class Record:
    pass


class Video:
    pass


class File:
    pass


class CommandFilter:
    pass


@dataclass
class _Handler:
    event_filters: list[object]


@dataclass
class _MessageObject:
    message_id: str
    timestamp: float = 1.0


@dataclass
class _Result:
    chain: list[object]


class FakeEvent:
    def __init__(
        self,
        text: str,
        *,
        message_id: str = "m1",
        private: bool = True,
        group_id: str = "",
        bot_directed: bool = False,
        messages: list[object] | None = None,
        activated_handlers: list[object] | None = None,
    ) -> None:
        self.message_obj = _MessageObject(message_id)
        self.unified_msg_origin = f"mock:{'private' if private else 'group'}:session"
        self._text = text
        self._private = private
        self._group_id = group_id
        self.is_at_or_wake_command = bot_directed
        self._messages = messages if messages is not None else [Plain(text)]
        self._extras = {"activated_handlers": activated_handlers or []}
        self._stopped = False
        self._result: _Result | None = None

    def is_private_chat(self) -> bool:
        return self._private

    def get_group_id(self) -> str:
        return self._group_id

    def get_session_id(self) -> str:
        return "session"

    def get_message_str(self) -> str:
        return self._text

    def get_messages(self) -> list[object]:
        return self._messages

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def stop_event(self) -> None:
        self._stopped = True

    def get_result(self):
        return self._result

    def plain_result(self, text: str) -> str:
        return text


class _Response:
    def __init__(self, text: str) -> None:
        self.completion_text = text


class FakeContext:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def llm_generate(self, **kwargs):
        self.calls.append(kwargs)
        return _Response(self.response)


def plugin_config(**overrides):
    config = {
        "enabled": True,
        "private_enabled": True,
        "group_enabled": False,
        "judge_provider_id": "judge",
        "history_limit": 10,
        "confidence_threshold": 0.85,
        "judge_timeout_seconds": 5.0,
        "debug_log": False,
        "session_ttl_minutes": 1440,
        "max_message_chars": 800,
        "max_context_chars": 6000,
        "judge_max_tokens": 160,
    }
    config.update(overrides)
    return config


@pytest.mark.asyncio
async def test_high_confidence_end_stops_event_silently() -> None:
    context = FakeContext(
        '{"decision":"END","confidence":0.95,"reason":"交流已经完成"}'
    )
    plugin = ConversationCloserPlugin(context, plugin_config())
    event = FakeEvent("可以")
    await plugin.on_message(event)

    assert event._stopped is True
    assert event.get_result() is None
    assert len(context.calls) == 1
    assert context.calls[0]["temperature"] == 0.0
    assert context.calls[0]["tools"] is None


@pytest.mark.asyncio
async def test_low_confidence_end_continues() -> None:
    context = FakeContext(
        '{"decision":"END","confidence":0.5,"reason":"可能已经完成"}'
    )
    plugin = ConversationCloserPlugin(context, plugin_config())
    event = FakeEvent("可以")
    await plugin.on_message(event)
    assert event._stopped is False


@pytest.mark.asyncio
async def test_uncertain_continues() -> None:
    context = FakeContext(
        '{"decision":"UNCERTAIN","confidence":0.7,"reason":"无法可靠判断"}'
    )
    plugin = ConversationCloserPlugin(context, plugin_config())
    event = FakeEvent("嗯？")
    await plugin.on_message(event)
    assert event._stopped is False


@pytest.mark.asyncio
async def test_missing_provider_fails_open_and_keeps_history() -> None:
    context = FakeContext('{"decision":"END","confidence":1,"reason":"完成"}')
    plugin = ConversationCloserPlugin(context, plugin_config(judge_provider_id=""))
    event = FakeEvent("需要正常处理的问题")
    await plugin.on_message(event)
    assert event._stopped is False
    assert context.calls == []
    history = await plugin.store.snapshot(event.unified_msg_origin)
    assert history[-1].content == "需要正常处理的问题"


@pytest.mark.asyncio
async def test_disabled_and_private_disabled_do_not_intervene() -> None:
    response = '{"decision":"END","confidence":1,"reason":"完成"}'
    disabled_context = FakeContext(response)
    disabled = ConversationCloserPlugin(disabled_context, plugin_config(enabled=False))
    await disabled.on_message(FakeEvent("好"))
    assert disabled_context.calls == []

    private_context = FakeContext(response)
    private_off = ConversationCloserPlugin(
        private_context,
        plugin_config(private_enabled=False),
    )
    await private_off.on_message(FakeEvent("好"))
    assert private_context.calls == []


@pytest.mark.asyncio
async def test_group_disabled_continues_without_judge() -> None:
    context = FakeContext('{"decision":"END","confidence":1,"reason":"完成"}')
    plugin = ConversationCloserPlugin(context, plugin_config(group_enabled=False))
    event = FakeEvent("好", private=False, group_id="group-1")
    await plugin.on_message(event)
    assert event._stopped is False
    assert context.calls == []


@pytest.mark.asyncio
async def test_group_enabled_requires_explicit_bot_direction() -> None:
    response = '{"decision":"END","confidence":1,"reason":"完成"}'
    context = FakeContext(response)
    plugin = ConversationCloserPlugin(context, plugin_config(group_enabled=True))
    unrelated = FakeEvent("好", private=False, group_id="group-1")
    directed = FakeEvent(
        "好",
        message_id="m2",
        private=False,
        group_id="group-1",
        bot_directed=True,
    )

    await plugin.on_message(unrelated)
    await plugin.on_message(directed)
    assert unrelated._stopped is False
    assert directed._stopped is True
    assert len(context.calls) == 1


@pytest.mark.asyncio
async def test_commands_are_never_judged() -> None:
    context = FakeContext('{"decision":"END","confidence":1,"reason":"完成"}')
    plugin = ConversationCloserPlugin(context, plugin_config())
    slash_event = FakeEvent("/closer status")
    metadata_event = FakeEvent(
        "closer status",
        message_id="m2",
        activated_handlers=[_Handler([CommandFilter()])],
    )
    await plugin.on_message(slash_event)
    await plugin.on_message(metadata_event)
    assert context.calls == []
    assert slash_event._stopped is False
    assert metadata_event._stopped is False


@pytest.mark.asyncio
async def test_assistant_history_records_plain_and_media_after_send() -> None:
    context = FakeContext(
        '{"decision":"CONTINUE","confidence":1,"reason":"继续"}'
    )
    plugin = ConversationCloserPlugin(context, plugin_config())
    event = FakeEvent("问题")
    event._result = _Result([Plain("回答"), Image(), Record(), Video(), File()])
    await plugin.capture_outgoing_result(event)
    event._result = _Result([Plain("回答")])
    await plugin.after_message_sent(event)
    history = await plugin.store.snapshot(event.unified_msg_origin)
    assert [item.content for item in history] == [
        "回答\n[图片]\n[语音]\n[视频]\n[文件]"
    ]


@pytest.mark.asyncio
async def test_media_only_user_message_never_gets_swallowed() -> None:
    context = FakeContext('{"decision":"END","confidence":1,"reason":"完成"}')
    plugin = ConversationCloserPlugin(context, plugin_config())
    event = FakeEvent("", messages=[Image()])
    await plugin.on_message(event)
    assert event._stopped is False
    assert context.calls == []
    history = await plugin.store.snapshot(event.unified_msg_origin)
    assert history[-1].content == "[图片]"


@pytest.mark.asyncio
async def test_status_clear_test_commands_and_terminate() -> None:
    context = FakeContext(
        '{"decision":"CONTINUE","confidence":1,"reason":"仍需继续"}'
    )
    plugin = ConversationCloserPlugin(context, plugin_config())
    event = FakeEvent("普通消息")
    await plugin.on_message(event)

    status = [item async for item in plugin.closer_status(event)]
    latest = [item async for item in plugin.closer_test(event)]
    cleared = [item async for item in plugin.closer_clear(event)]
    assert "Conversation Closer 状态" in status[0]
    assert "decision: CONTINUE" in latest[0]
    assert "已清除" in cleared[0]

    await plugin.terminate()
    await plugin.terminate()
    assert plugin.store.session_count == 0


def test_debug_log_omits_reason_and_uses_process_keyed_session_ids(caplog) -> None:
    first = ConversationCloserPlugin(
        FakeContext(""),
        plugin_config(debug_log=True),
    )
    second = ConversationCloserPlugin(
        FakeContext(""),
        plugin_config(debug_log=True),
    )
    session_id = "mock:private:123456"
    first_id = first._masked_session(session_id)  # noqa: SLF001 - privacy invariant
    assert first_id == first._masked_session(session_id)  # noqa: SLF001
    assert first_id != second._masked_session(session_id)  # noqa: SLF001

    caplog.set_level(logging.INFO, logger="astrbot-test")
    first._debug_result(  # noqa: SLF001 - privacy invariant
        session_id,
        JudgeResult(
            decision=Decision.END,
            confidence=0.95,
            reason="private-message-secret",
        ),
        duplicate=False,
    )
    assert "private-message-secret" not in caplog.text
    assert session_id not in caplog.text
    assert first_id in caplog.text
