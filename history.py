"""Bounded, session-isolated in-memory conversation history."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from .models import HistoryMessage, JudgeResult


@dataclass(frozen=True, slots=True)
class ProcessedMessage:
    """一次已处理事件的去重信息，不保存额外明文。"""

    content_fingerprint: bytes
    result: JudgeResult
    judged: bool


@dataclass(slots=True)
class SessionState:
    """Mutable data protected by one session-specific lock."""

    history: deque[HistoryMessage]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    processed: OrderedDict[str, ProcessedMessage] = field(default_factory=OrderedDict)
    last_judge: JudgeResult | None = None
    updated_at: float = 0.0
    dropped_message_count: int = 0


class SessionStore:
    """Keep histories bounded without serializing unrelated sessions."""

    def __init__(
        self,
        *,
        history_limit: int,
        ttl_seconds: float,
        message_cache_limit: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._history_limit = history_limit
        self._ttl_seconds = ttl_seconds
        self._message_cache_limit = message_cache_limit or max(64, history_limit * 8)
        self._clock = clock
        self._states: dict[str, SessionState] = {}
        self._last_cleanup = 0.0
        self._cleanup_interval = min(max(ttl_seconds / 10, 30.0), 600.0)
        self._closed = False

    @property
    def session_count(self) -> int:
        return len(self._states)

    def _get_or_create(self, session_id: str) -> SessionState:
        if self._closed:
            raise RuntimeError("session store is closed")
        state = self._states.get(session_id)
        if state is None:
            state = SessionState(
                history=deque(maxlen=self._history_limit),
                updated_at=self._clock(),
            )
            self._states[session_id] = state
        return state

    def cleanup_stale(self, *, force: bool = False) -> int:
        """Lazily remove idle, unlocked sessions."""

        now = self._clock()
        if not force and now - self._last_cleanup < self._cleanup_interval:
            return 0
        self._last_cleanup = now
        stale = [
            session_id
            for session_id, state in self._states.items()
            if not state.lock.locked() and now - state.updated_at >= self._ttl_seconds
        ]
        for session_id in stale:
            self._states.pop(session_id, None)
        return len(stale)

    @asynccontextmanager
    async def locked(self, session_id: str) -> AsyncIterator[SessionState]:
        """Lock exactly one session for ordered append-and-judge processing."""

        self.cleanup_stale()
        state = self._get_or_create(session_id)
        async with state.lock:
            if self._closed:
                raise RuntimeError("session store is closed")
            state.updated_at = self._clock()
            try:
                yield state
            finally:
                state.updated_at = self._clock()

    def append_message(
        self,
        state: SessionState,
        *,
        role: str,
        content: str,
        timestamp: float,
    ) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("unsupported history role")
        if state.history.maxlen is not None and len(state.history) >= state.history.maxlen:
            state.dropped_message_count += 1
        state.history.append(
            HistoryMessage(role=role, content=content, timestamp=timestamp)  # type: ignore[arg-type]
        )

    @staticmethod
    def reset_history(state: SessionState) -> None:
        """开始新的对话阶段，同时保留去重结果和最近判断。"""

        state.history.clear()
        state.dropped_message_count = 0

    @staticmethod
    def get_processed(
        state: SessionState,
        message_id: str | None,
        content_fingerprint: bytes,
    ) -> ProcessedMessage | None:
        if not message_id:
            return None
        processed = state.processed.get(message_id)
        if processed is not None and processed.content_fingerprint == content_fingerprint:
            state.processed.move_to_end(message_id)
            return processed
        return None

    def remember_processed(
        self,
        state: SessionState,
        message_id: str | None,
        content_fingerprint: bytes,
        result: JudgeResult,
        *,
        judged: bool,
    ) -> None:
        if not message_id:
            return
        state.processed[message_id] = ProcessedMessage(
            content_fingerprint=content_fingerprint,
            result=result,
            judged=judged,
        )
        state.processed.move_to_end(message_id)
        while len(state.processed) > self._message_cache_limit:
            state.processed.popitem(last=False)

    async def record_assistant(
        self,
        session_id: str,
        content: str,
        timestamp: float,
    ) -> None:
        async with self.locked(session_id) as state:
            self.append_message(
                state,
                role="assistant",
                content=content,
                timestamp=timestamp,
            )

    async def snapshot(self, session_id: str) -> tuple[HistoryMessage, ...]:
        state = self._states.get(session_id)
        if state is None:
            return ()
        async with state.lock:
            return tuple(state.history)

    async def last_judge(self, session_id: str) -> JudgeResult | None:
        state = self._states.get(session_id)
        if state is None:
            return None
        async with state.lock:
            return state.last_judge

    async def clear(self, session_id: str) -> int:
        state = self._states.get(session_id)
        if state is None:
            return 0
        async with state.lock:
            count = len(state.history)
            self.reset_history(state)
            state.processed.clear()
            state.last_judge = None
            state.updated_at = self._clock()
            return count

    async def close(self) -> None:
        """Release all in-memory resources; no background task is created."""

        self._closed = True
        states = tuple(self._states.values())
        self._states.clear()
        for state in states:
            async with state.lock:
                state.history.clear()
                state.processed.clear()
                state.last_judge = None
                state.dropped_message_count = 0
