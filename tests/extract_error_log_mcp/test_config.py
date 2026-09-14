"""extract_error_log_mcp 설정 모듈 테스트."""

from unittest.mock import patch

import pytest

from extract_error_log_mcp.config import (
    DEFAULT_SSL_VERIFY,
    DEFAULT_TIMEOUT,
    EXTRACT_LOG_PATH,
    MDCONTENT_GET_PATH,
    MDCONTENT_LIST_PATH,
    Settings,
)
from mcp_common.config import DEFAULT_MAX_RESPONSE_BYTES, MAX_RESPONSE_BYTES_ENV


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("extract_error_log_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def _env(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    monkeypatch.delenv("API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv(MAX_RESPONSE_BYTES_ENV, raising=False)


class TestRequiredSettings:
    """필수 환경변수 처리."""

    def test_loads_required_values(self, _env):
        settings = Settings()

        assert settings.api_base_url == "https://app.mwm.local:20443"
        assert settings.api_bearer_token == "secret-token"

    def test_missing_base_url_raises(self, monkeypatch, _env):
        monkeypatch.delenv("API_BASE_URL", raising=False)

        with pytest.raises(ValueError, match="API_BASE_URL"):
            Settings()

    def test_missing_token_raises(self, monkeypatch, _env):
        monkeypatch.delenv("API_BEARER_TOKEN", raising=False)

        with pytest.raises(ValueError, match="API_BEARER_TOKEN"):
            Settings()

    def test_blank_token_raises(self, monkeypatch, _env):
        """빈 문자열도 미설정으로 취급한다."""
        monkeypatch.setenv("API_BEARER_TOKEN", "")

        with pytest.raises(ValueError, match="API_BEARER_TOKEN"):
            Settings()


class TestOptionalSettings:
    """선택 환경변수의 기본값과 파싱."""

    def test_ssl_verify_defaults(self, _env):
        assert Settings().api_ssl_verify is DEFAULT_SSL_VERIFY

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes"])
    def test_ssl_verify_truthy_values(self, monkeypatch, _env, value):
        monkeypatch.setenv("API_SSL_VERIFY", value)

        assert Settings().api_ssl_verify is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "아무거나"])
    def test_ssl_verify_falsy_values(self, monkeypatch, _env, value):
        monkeypatch.setenv("API_SSL_VERIFY", value)

        assert Settings().api_ssl_verify is False

    def test_timeout_defaults(self, _env):
        assert Settings().api_timeout == DEFAULT_TIMEOUT

    def test_timeout_from_env(self, monkeypatch, _env):
        monkeypatch.setenv("API_TIMEOUT", "120")

        assert Settings().api_timeout == 120


class TestDerivedUrls:
    """설정값으로 조립되는 URL과 헤더."""

    def test_extract_log_url(self, _env):
        assert Settings().extract_log_url == (
            f"https://app.mwm.local:20443{EXTRACT_LOG_PATH}"
        )

    def test_mdcontent_list_url(self, _env):
        assert Settings().mdcontent_list_url == (
            f"https://app.mwm.local:20443{MDCONTENT_LIST_PATH}"
        )

    def test_mdcontent_get_url_embeds_content_id(self, _env):
        expected = "https://app.mwm.local:20443" + MDCONTENT_GET_PATH.format(
            content_id=42
        )

        assert Settings().get_mdcontent_url(42) == expected

    def test_auth_header(self, _env):
        assert Settings().auth_header == {"Authorization": "Bearer secret-token"}


class TestResponseSizeLimitSetting:
    """응답 크기 한도 설정."""

    def test_defaults_to_30k(self, _env):
        """MCP_MAX_RESPONSE_BYTES 미설정 시 기본값 30,000 바이트를 쓴다."""
        assert Settings().max_response_bytes == DEFAULT_MAX_RESPONSE_BYTES

    def test_reads_limit_from_env(self, monkeypatch, _env):
        """환경변수로 응답 크기 한도를 조정할 수 있다."""
        monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "12345")

        assert Settings().max_response_bytes == 12345
