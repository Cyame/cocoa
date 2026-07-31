"""PRD-v3.4.1 composer turns + mention parse."""

from __future__ import annotations

import pytest

from app.core.composer_turns import _iter_tokens, get_turn, schedule_user_turn
from app.core.slash_parser import parse_turn


@pytest.mark.asyncio
async def test_stub_token_stream_yields_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    tokens: list[str] = []
    finish = None
    async for chunk in _iter_tokens("ping"):
        if chunk.token:
            tokens.append(chunk.token)
        if chunk.finish_reason:
            finish = chunk.finish_reason
    assert "".join(tokens) == "[stub] ping"
    assert finish == "stop"


def test_parse_turn_multi_mention_chat() -> None:
    turn = parse_turn("@a 你好\n@b hello")
    assert len(turn.directives) == 2
    assert turn.directives[0].target_entity == "a"
    assert turn.directives[0].cmd == ""
    assert turn.directives[0].args == ["你好"]
    assert turn.directives[1].target_entity == "b"
    assert turn.directives[1].args == ["hello"]


@pytest.mark.asyncio
async def test_schedule_user_turn_registers_state(session) -> None:
    """schedule_user_turn creates in-memory turn + emits without requiring LLM key."""
    turn_id = await schedule_user_turn(
        session=session,
        workspace_id="ws-test",
        instance_id="inst-test",
        target_entity="alice",
        text="hi",
        cmd=None,
        from_membership_id="mem-test",
    )
    state = get_turn(turn_id)
    assert state is not None
    assert state.status == "responding"
    assert state.target_entity == "alice"
