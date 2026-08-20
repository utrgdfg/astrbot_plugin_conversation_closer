"""AstrBot adapter for Conversation Closer."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Mapping, MutableMapping
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .history import SessionStore
from .judge import LLMJudge
from .message_utils import extract_message_chain
from .models import JudgeResult
from .service import ConversationCloserService, UserMessage
from .settings import PluginSettings, migrate_legacy_config

# Positive priorities run first. AstrBot's built-ins reserve sys.maxsize values;
# 100 intentionally runs before ordinary priority-0 plugin handlers without
# attempting to outrank core safety handlers.
INTERCEPT_PRIORITY = 100
AFTER_SENT_PRIORITY = 100
OUTGOING_CAPTURE_PRIORITY = -100
OUTGOING_SNAPSHOT_KEY = "conversation_closer.outgoing_snapshot"


class ConversationCloserPlugin(Star):
    """Silently stop only high-confidence, semantically complete exchanges."""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        try:
            if isinstance(config, MutableMapping) and migrate_legacy_config(config):
                save_config = getattr(config, "save_config", None)
                if callable(save_config):
                    save_config()
                logger.info("[ConversationCloser] 已迁移旧版插件配置")
        except Exception as exc:  # noqa: BLE001 - configuration remains fail-open
            logger.warning(
                "[ConversationCloser] 配置迁移未能保存：%s",
                type(exc).__name__,
            )
        config_mapping: Mapping[str, Any] = config
        self.settings = PluginSettings.from_mapping(config_mapping)
        self._log_id_key = secrets.token_bytes(32)
        self.store = SessionStore(
            history_limit=self.settings.history_limit,
            ttl_seconds=self.settings.session_ttl_minutes * 60,
        )
        self.judge = LLMJudge(
            self._generate_judgement,
            timeout_seconds=self.settings.judge_timeout_seconds,
            max_message_chars=self.settings.max_message_chars,
            max_context_chars=self.settings.max_context_chars,
        )
        self.service = ConversationCloserService(
            self.settings,
            self.store,
            self.judge,
        )
        logger.info(
            "[ConversationCloser] 已初始化：启用=%s 私聊=%s 群聊=%s",
            self.settings.enabled,
            self.settings.private_enabled,
            self.settings.group_enabled,
        )

    async def _generate_judgement(self, system_prompt: str, prompt: str) -> str:
        """Call exactly one configured AstrBot chat provider without tools."""

        response = await self.context.llm_generate(
            chat_provider_id=self.settings.judge_provider_id,
            prompt=prompt,
            system_prompt=system_prompt,
            contexts=[],
            tools=None,
            temperature=0.0,
            max_tokens=self.settings.judge_max_tokens,
        )
        completion = response.completion_text
        return completion if isinstance(completion, str) else ""

    @staticmethod
    def _session_id(event: AstrMessageEvent) -> str:
        unified = getattr(event, "unified_msg_origin", "")
        if isinstance(unified, str) and unified.strip():
            return unified.strip()
        try:
            fallback = event.get_session_id()
        except Exception:  # noqa: BLE001 - adapter boundary
            return ""
        return fallback.strip() if isinstance(fallback, str) else ""

    @staticmethod
    def _message_id(event: AstrMessageEvent) -> str | None:
        message_obj = getattr(event, "message_obj", None)
        message_id = getattr(message_obj, "message_id", None)
        if message_id is None:
            return None
        normalized = str(message_id).strip()
        return normalized or None

    @staticmethod
    def _timestamp(event: AstrMessageEvent) -> float:
        message_obj = getattr(event, "message_obj", None)
        timestamp = getattr(message_obj, "timestamp", None)
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            return time.time()
        return float(timestamp)

    @staticmethod
    def _is_supported_channel(event: AstrMessageEvent) -> tuple[bool, bool]:
        try:
            if event.is_private_chat():
                return True, True
            group_id = event.get_group_id()
        except Exception:  # noqa: BLE001 - adapter boundary
            return False, False
        is_bot_directed = bool(getattr(event, "is_at_or_wake_command", False))
        return (True, False) if group_id and is_bot_directed else (False, False)

    @staticmethod
    def _is_command(event: AstrMessageEvent) -> bool:
        """Use WakingCheck's activated command handlers when available."""

        try:
            handlers = event.get_extra("activated_handlers", []) or []
        except Exception:  # noqa: BLE001 - adapter boundary
            handlers = []
        for handler in handlers:
            event_filters = getattr(handler, "event_filters", ()) or ()
            if any(type(item).__name__ == "CommandFilter" for item in event_filters):
                return True
        # Covers the default slash prefix when handler metadata is unavailable.
        try:
            return event.get_message_str().lstrip().startswith("/")
        except Exception:  # noqa: BLE001 - adapter boundary
            return False

    def _masked_session(self, session_id: str) -> str:
        return hmac.new(
            self._log_id_key,
            session_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:10]

    def _debug_result(
        self,
        session_id: str,
        result: JudgeResult | None,
        *,
        duplicate: bool,
    ) -> None:
        if not self.settings.debug_log or result is None:
            return
        logger.info(
            "[ConversationCloser] 会话=%s 判断=%s 可信度=%.3f "
            "耗时=%.3f秒 重复=%s 错误=%s",
            self._masked_session(session_id),
            result.decision.value,
            result.confidence,
            result.elapsed_seconds,
            duplicate,
            result.error_code or "无",
        )

    @filter.event_message_type(filter.EventMessageType.ALL, priority=INTERCEPT_PRIORITY)
    async def on_message(self, event: AstrMessageEvent) -> None:
        """Judge before AstrBot reaches its default LLM request."""

        try:
            supported, is_private = self._is_supported_channel(event)
            if not supported:
                return
            session_id = self._session_id(event)
            text = event.get_message_str()
            outline = extract_message_chain(event.get_messages())
            outcome = await self.service.process_user(
                UserMessage(
                    session_id=session_id,
                    message_id=self._message_id(event),
                    text=text if isinstance(text, str) else "",
                    outline=outline,
                    timestamp=self._timestamp(event),
                    is_private=is_private,
                    is_command=self._is_command(event),
                )
            )
            self._debug_result(
                session_id,
                outcome.result,
                duplicate=outcome.duplicate,
            )
            if outcome.should_stop:
                event.stop_event()
        except Exception as exc:  # noqa: BLE001 - final fail-open boundary
            logger.warning(
                "[ConversationCloser] 消息处理异常，已正常放行：%s",
                type(exc).__name__,
            )

    @filter.on_decorating_result(priority=OUTGOING_CAPTURE_PRIORITY)
    async def capture_outgoing_result(self, event: AstrMessageEvent) -> None:
        """Snapshot the decorated chain before RespondStage may remove media parts."""

        try:
            supported, is_private = self._is_supported_channel(event)
            if (
                not supported
                or not self.service.channel_enabled(is_private)
                or self._is_command(event)
            ):
                return
            result = event.get_result()
            content = extract_message_chain(getattr(result, "chain", None))
            if content:
                event.set_extra(OUTGOING_SNAPSHOT_KEY, content)
        except Exception as exc:  # noqa: BLE001 - decoration must remain non-blocking
            logger.warning(
                "[ConversationCloser] 机器人回复快照记录失败：%s",
                type(exc).__name__,
            )

    @filter.after_message_sent(priority=AFTER_SENT_PRIORITY)
    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        """Record only a result that reached AstrBot's post-send hook."""

        try:
            supported, is_private = self._is_supported_channel(event)
            if (
                not supported
                or not self.service.channel_enabled(is_private)
                or self._is_command(event)
            ):
                return
            content = event.get_extra(OUTGOING_SNAPSHOT_KEY, "")
            event.set_extra(OUTGOING_SNAPSHOT_KEY, None)
            if not isinstance(content, str) or not content:
                result = event.get_result()
                chain = getattr(result, "chain", None)
                content = extract_message_chain(chain)
            if not content:
                return
            await self.service.record_assistant(
                session_id=self._session_id(event),
                content=content,
            )
        except Exception as exc:  # noqa: BLE001 - post-send must not break pipeline
            logger.warning(
                "[ConversationCloser] 机器人回复历史记录失败：%s",
                type(exc).__name__,
            )

    @filter.command_group("closer")
    def closer():
        """Conversation Closer session commands."""

        pass

    @closer.command("status")
    async def closer_status(self, event: AstrMessageEvent):
        """Show effective configuration and current cache size."""

        session_id = self._session_id(event)
        history = await self.store.snapshot(session_id) if session_id else ()
        provider = self.settings.judge_provider_id or "未选择（消息会正常放行）"
        enabled = "已开启" if self.settings.enabled else "已关闭"
        private = "已开启" if self.settings.private_enabled else "已关闭"
        group = "已开启" if self.settings.group_enabled else "已关闭"
        yield event.plain_result(
            "对话自然收尾状态\n"
            f"- 插件：{enabled}\n"
            f"- 私聊：{private}\n"
            f"- 群聊（实验）：{group}\n"
            f"- 对话判断模型：{provider}\n"
            f"- 参考最近消息数：{self.settings.history_limit}\n"
            f"- 结束判断门槛：{self.settings.confidence_threshold:.2f}\n"
            f"- 当前会话记录：{len(history)} 条"
        )

    @closer.command("clear")
    async def closer_clear(self, event: AstrMessageEvent):
        """Clear only the current session's in-memory context."""

        session_id = self._session_id(event)
        cleared = await self.store.clear(session_id) if session_id else 0
        yield event.plain_result(f"已清除当前会话的 {cleared} 条收尾判断上下文。")

    @closer.command("test")
    async def closer_test(self, event: AstrMessageEvent):
        """Show the latest validated judge result for this session."""

        session_id = self._session_id(event)
        result = await self.store.last_judge(session_id) if session_id else None
        if result is None:
            yield event.plain_result("当前会话还没有判断结果。")
            return
        decision_labels = {
            "END": "对话已结束",
            "CONTINUE": "继续正常回复",
            "UNCERTAIN": "无法确定，正常放行",
        }
        yield event.plain_result(
            "最近一次判断\n"
            f"- 结果：{decision_labels[result.decision.value]}\n"
            f"- 可信度：{result.confidence:.3f}\n"
            f"- 原因：{result.reason}\n"
            f"- 耗时：{result.elapsed_seconds:.3f} 秒\n"
            f"- 异常放行：{'是' if result.error_code else '否'}"
        )

    async def terminate(self) -> None:
        """Release all caches; this plugin intentionally creates no background task."""

        await self.store.close()
        logger.info("[ConversationCloser] 已终止并清空内存会话历史")
