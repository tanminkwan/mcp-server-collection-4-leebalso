"""MCP 도구 응답의 크기를 제한하는 공통 가드.

MCP 서버가 AI Agent 에게 돌려주는 응답이 지나치게 크면 Agent 의 컨텍스트를 잠식하고
호출 자체가 실패할 수 있다. 한도를 넘으면 잘라서 돌려주는 대신 "너무 커서 줄 수 없다"는
오류를 명시적으로 발생시켜, Agent 가 조회 범위를 좁혀 재시도하도록 유도한다.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar, runtime_checkable

from mcp.server.mcpserver.exceptions import ToolError

from mcp_common.config import (
    MAX_RESPONSE_BYTES_ENV,
    RESPONSE_ENCODING,
    RESPONSE_TOO_LARGE_MESSAGE_TEMPLATE,
)


@runtime_checkable
class ResponseSizeLimited(Protocol):
    """응답 크기 한도를 제공하는 설정 객체의 계약.

    각 MCP 서버의 Settings 가 이 프로토콜을 구조적으로 만족하므로, 가드는 특정 서버의
    설정 클래스에 의존하지 않는다.
    """

    max_response_bytes: int


class ResponseTooLargeError(ToolError):
    """응답이 허용 한도를 초과했음을 알리는 오류.

    MCP 는 ToolError 의 메시지만 호출자에게 그대로 전달하므로(그 외 예외는 일반 문구로
    가려진다) ToolError 를 상속한다.
    """


def measure_response_bytes(response: str) -> int:
    """응답 문자열의 크기를 UTF-8 바이트 수로 잰다."""
    return len(response.encode(RESPONSE_ENCODING))


def enforce_response_size(response: str, limit: ResponseSizeLimited) -> str:
    """한도 이내면 응답을 그대로 반환하고, 초과하면 ResponseTooLargeError 를 발생시킨다."""
    actual_bytes = measure_response_bytes(response)
    max_bytes = limit.max_response_bytes
    if actual_bytes > max_bytes:
        raise ResponseTooLargeError(
            RESPONSE_TOO_LARGE_MESSAGE_TEMPLATE.format(
                actual_bytes=actual_bytes,
                max_bytes=max_bytes,
                env_name=MAX_RESPONSE_BYTES_ENV,
            )
        )
    return response


AsyncToolT = TypeVar("AsyncToolT", bound=Callable[..., Awaitable[str]])


def limit_response_size(
    limit: ResponseSizeLimited,
) -> Callable[[AsyncToolT], AsyncToolT]:
    """비동기 MCP 도구의 반환값에 응답 크기 한도를 적용하는 데코레이터.

    도구 본문은 그대로 두고 바깥에서 감싸므로, 도구가 자체 try/except 로 오류를 정상
    응답으로 바꾸더라도 크기 검사는 그 이후에 수행된다.
    """

    def decorator(fn: AsyncToolT) -> AsyncToolT:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return enforce_response_size(await fn(*args, **kwargs), limit)

        return wrapper  # type: ignore[return-value]

    return decorator
