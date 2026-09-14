"""MCP 서버 공통 설정 — 응답 크기 제한 관련 상수와 로더."""

from __future__ import annotations

import os

# AI Agent 에게 돌려줄 수 있는 응답의 최대 크기를 지정하는 환경변수 이름
MAX_RESPONSE_BYTES_ENV = "MCP_MAX_RESPONSE_BYTES"

# 환경변수 미설정 시 사용할 기본 한도 (UTF-8 바이트)
DEFAULT_MAX_RESPONSE_BYTES = 30_000

# 응답 크기를 재는 기준 인코딩 — 한글은 문자 수와 바이트 수가 다르므로 명시한다.
RESPONSE_ENCODING = "utf-8"

# 한도 초과 시 AI Agent 에게 전달할 오류 메시지
RESPONSE_TOO_LARGE_MESSAGE_TEMPLATE = (
    "응답 데이터가 너무 커서 반환할 수 없습니다 "
    "(응답 {actual_bytes:,}바이트 > 허용 한도 {max_bytes:,}바이트). "
    "조회 범위를 좁혀 다시 시도하세요 — 기간·대상·건수를 줄이거나 더 작은 파일을 "
    "지정하는 방법이 있습니다. 범위를 좁힐 수 없다면 사용자에게 응답이 너무 커서 "
    "가져올 수 없다는 사실과 그 이유를 알리세요. "
    "한도는 MCP 서버의 {env_name} 환경변수로 조정할 수 있습니다."
)

# 환경변수 값이 양의 정수가 아닐 때의 오류 메시지
INVALID_MAX_RESPONSE_BYTES_MESSAGE_TEMPLATE = (
    "환경변수 {env_name}은(는) 1 이상의 정수여야 합니다: '{value}'"
)


def load_max_response_bytes() -> int:
    """응답 크기 한도를 환경변수에서 로드한다 (미설정 시 기본값).

    잘못된 값은 서버 기동 시점에 즉시 실패시켜, 도구 호출 도중에 한도가 없는 상태로
    거대한 응답이 나가는 일이 없도록 한다.
    """
    raw = os.getenv(MAX_RESPONSE_BYTES_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_MAX_RESPONSE_BYTES

    value = raw.strip()
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(
            INVALID_MAX_RESPONSE_BYTES_MESSAGE_TEMPLATE.format(
                env_name=MAX_RESPONSE_BYTES_ENV, value=raw
            )
        ) from exc
    if parsed < 1:
        raise ValueError(
            INVALID_MAX_RESPONSE_BYTES_MESSAGE_TEMPLATE.format(
                env_name=MAX_RESPONSE_BYTES_ENV, value=raw
            )
        )
    return parsed
