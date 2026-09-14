"""mcp_common 응답 크기 제한 설정 테스트."""

import pytest

from mcp_common.config import (
    DEFAULT_MAX_RESPONSE_BYTES,
    INVALID_MAX_RESPONSE_BYTES_MESSAGE_TEMPLATE,
    MAX_RESPONSE_BYTES_ENV,
    load_max_response_bytes,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(MAX_RESPONSE_BYTES_ENV, raising=False)


def test_default_is_30k():
    """환경변수가 없으면 기본값 30,000 바이트를 사용한다."""
    assert DEFAULT_MAX_RESPONSE_BYTES == 30_000
    assert load_max_response_bytes() == DEFAULT_MAX_RESPONSE_BYTES


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "1024")
    assert load_max_response_bytes() == 1024


def test_blank_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "   ")
    assert load_max_response_bytes() == DEFAULT_MAX_RESPONSE_BYTES


@pytest.mark.parametrize("value", ["0", "-1", "abc", "10.5"])
def test_invalid_env_raises_value_error(monkeypatch, value):
    """양의 정수가 아니면 서버 기동 시점에 즉시 실패한다."""
    monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, value)
    with pytest.raises(ValueError) as exc_info:
        load_max_response_bytes()
    assert MAX_RESPONSE_BYTES_ENV in str(exc_info.value)
    assert str(exc_info.value) == INVALID_MAX_RESPONSE_BYTES_MESSAGE_TEMPLATE.format(
        env_name=MAX_RESPONSE_BYTES_ENV, value=value
    )
