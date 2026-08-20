"""Framework-independent orchestration for the conversation-closing decision."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from .history import SessionStore
from .judge import LLMJudge
from .message_utils import bound_text
from .models import Decision, JudgeResult
from .settings import PluginSettings


@dataclass(frozen=True, slots=True)
class UserMessage:
    session_id: str
    message_id: str | None
    text: str
    outline: str
    timestamp: float
    is_private: bool
    is_command: bool


@dataclass(frozen=True, slots=True)
class ProcessResult:
    should_stop: bool
    judged: bool
    duplicate: bool
    result: JudgeResult | None = None


class ConversationCloserService:
    """Apply conservative gates, ordered history, and strict END thresholding."""

    def __init__(
        self,
        settings: PluginSettings,
        store: SessionStore,
        judge: LLMJudge,
    ) -> None:
        self.settings = settings
        self.store = store
        self.judge = judge

    def channel_enabled(self, is_private: bool) -> bool:
        if not self.settings.enabled:
            return False
        return (
            self.settings.private_enabled
            if is_private
            else self.settings.group_enabled
        )

    def _should_stop(self, result: JudgeResult) -> bool:
        return (
            result.decision is Decision.END
            and result.confidence >= self.settings.confidence_threshold
        )

    async def process_user(self, message: UserMessage) -> ProcessResult:
        """Judge one eligible event; every error path remains non-blocking."""

        if not self.channel_enabled(message.is_private) or message.is_command:
            return ProcessResult(should_stop=False, judged=False, duplicate=False)
        if not message.session_id:
            return ProcessResult(
                should_stop=False,
                judged=False,
                duplicate=False,
                result=JudgeResult.fail_open(
                    "无法取得会话标识，已正常放行",
                    error_code="missing_session",
                ),
            )

        content = bound_text(message.text or message.outline, self.settings.max_message_chars)
        if not content:
            return ProcessResult(should_stop=False, judged=False, duplicate=False)

        try:
            async with self.store.locked(message.session_id) as state:
                cached = self.store.get_processed(state, message.message_id)
                if cached is not None:
                    return ProcessResult(
                        should_stop=self._should_stop(cached),
                        judged=True,
                        duplicate=True,
                        result=cached,
                    )

                self.store.append_message(
                    state,
                    role="user",
                    content=content,
                    timestamp=message.timestamp,
                )

                if not message.text.strip():
                    result = JudgeResult.fail_open(
                        "消息没有可供可靠判断的文本，已正常放行",
                        error_code="no_text",
                    )
                    judged = False
                elif not self.settings.judge_provider_id:
                    result = JudgeResult.fail_open(
                        "未选择对话判断模型，消息已正常放行",
                        error_code="provider_not_configured",
                    )
                    judged = False
                else:
                    result = await self.judge.evaluate(tuple(state.history))
                    judged = True

                state.last_judge = result
                self.store.remember_processed(state, message.message_id, result)
                return ProcessResult(
                    should_stop=self._should_stop(result),
                    judged=judged,
                    duplicate=False,
                    result=result,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - outer fail-open boundary
            return ProcessResult(
                should_stop=False,
                judged=False,
                duplicate=False,
                result=JudgeResult.fail_open(
                    "插件内部异常，已正常放行",
                    error_code=f"internal_{type(exc).__name__}",
                ),
            )

    async def record_assistant(
        self,
        *,
        session_id: str,
        content: str,
        timestamp: float | None = None,
    ) -> bool:
        if not self.settings.enabled or not session_id or not content.strip():
            return False
        bounded = bound_text(content, self.settings.max_message_chars)
        await self.store.record_assistant(
            session_id,
            bounded,
            time.time() if timestamp is None else timestamp,
        )
        return True
