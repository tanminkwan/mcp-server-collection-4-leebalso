"""mcp_common 응답 크기 제한 가드 테스트."""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_common.config import RESPONSE_TOO_LARGE_MESSAGE_TEMPLATE, MAX_RESPONSE_BYTES_ENV
from mcp_common.response_limit import (
    ResponseTooLargeError,
    enforce_response_size,
    limit_response_size,
    measure_response_bytes,
)


class _Limit:
    """ResponseSizeLimited 프로토콜을 만족하는 테스트용 설정 객체."""

    def __init__(self, max_response_bytes: int) -> None:
        self.max_response_bytes = max_response_bytes


def test_measure_counts_utf8_bytes_not_characters():
    """한글은 문자 수가 아니라 UTF-8 바이트 수로 센다."""
    assert measure_response_bytes("가나다") == 9
    assert measure_response_bytes("abc") == 3


def test_enforce_returns_response_within_limit():
    assert enforce_response_size("abc", _Limit(3)) == "abc"


def test_enforce_raises_when_over_limit():
    with pytest.raises(ResponseTooLargeError) as exc_info:
        enforce_response_size("abcd", _Limit(3))
    assert str(exc_info.value) == RESPONSE_TOO_LARGE_MESSAGE_TEMPLATE.format(
        actual_bytes=4, max_bytes=3, env_name=MAX_RESPONSE_BYTES_ENV
    )


def test_error_message_states_it_is_too_large_to_return():
    with pytest.raises(ResponseTooLargeError) as exc_info:
        enforce_response_size("x" * 10, _Limit(1))
    message = str(exc_info.value)
    assert "너무 커서" in message
    assert "10" in message and "1" in message


def test_error_is_a_tool_error_so_the_agent_sees_the_message():
    """MCP 는 ToolError 의 메시지만 AI Agent 에게 그대로 전달한다."""
    assert issubclass(ResponseTooLargeError, ToolError)


async def test_decorator_passes_through_small_response():
    @limit_response_size(_Limit(100))
    async def tool(value: str) -> str:
        """도구 설명."""
        return value

    assert await tool("작은 응답") == "작은 응답"


async def test_decorator_raises_on_large_response():
    @limit_response_size(_Limit(10))
    async def tool() -> str:
        return "x" * 11

    with pytest.raises(ResponseTooLargeError):
        await tool()


async def test_decorator_preserves_signature_and_docstring():
    """MCP 는 함수 시그니처·docstring 으로 도구 스키마를 만들므로 보존돼야 한다."""
    import inspect

    @limit_response_size(_Limit(100))
    async def tool(value: str, count: int = 1) -> str:
        """도구 설명."""
        return value * count

    assert tool.__name__ == "tool"
    assert tool.__doc__ == "도구 설명."
    assert list(inspect.signature(tool).parameters) == ["value", "count"]
