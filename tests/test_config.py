"""config 모듈 테스트."""

import os
from unittest.mock import patch

import pytest

from email_mcp.config import Settings
from mcp_common.config import DEFAULT_MAX_RESPONSE_BYTES, MAX_RESPONSE_BYTES_ENV


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("email_mcp.config.load_dotenv"):
        yield


class TestSettings:
    """Settings 클래스 테스트."""

    def test_load_from_env(self, monkeypatch):
        """환경변수에서 설정값을 로드한다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com:8443")
        monkeypatch.setenv("API_BEARER_TOKEN", "test-token-123")
        monkeypatch.setenv("API_SSL_VERIFY", "true")

        settings = Settings()

        assert settings.api_base_url == "https://test.example.com:8443"
        assert settings.api_bearer_token == "test-token-123"
        assert settings.api_ssl_verify is True

    def test_ssl_verify_defaults_to_false(self, monkeypatch):
        """API_SSL_VERIFY 미설정 시 기본값은 False이다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com")
        monkeypatch.setenv("API_BEARER_TOKEN", "token")
        monkeypatch.delenv("API_SSL_VERIFY", raising=False)

        settings = Settings()

        assert settings.api_ssl_verify is False

    def test_missing_base_url_raises(self, monkeypatch):
        """API_BASE_URL 누락 시 에러를 발생시킨다."""
        monkeypatch.delenv("API_BASE_URL", raising=False)
        monkeypatch.setenv("API_BEARER_TOKEN", "token")

        with pytest.raises(ValueError, match="API_BASE_URL"):
            Settings()

    def test_missing_bearer_token_raises(self, monkeypatch):
        """API_BEARER_TOKEN 누락 시 에러를 발생시킨다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com")
        monkeypatch.delenv("API_BEARER_TOKEN", raising=False)

        with pytest.raises(ValueError, match="API_BEARER_TOKEN"):
            Settings()

    def test_ssl_verify_false_string(self, monkeypatch):
        """API_SSL_VERIFY='false' 문자열을 False로 변환한다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com")
        monkeypatch.setenv("API_BEARER_TOKEN", "token")
        monkeypatch.setenv("API_SSL_VERIFY", "false")

        settings = Settings()

        assert settings.api_ssl_verify is False

    def test_email_send_url(self, monkeypatch):
        """이메일 발송 엔드포인트 URL을 올바르게 생성한다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com:8443")
        monkeypatch.setenv("API_BEARER_TOKEN", "token")

        settings = Settings()

        assert settings.email_send_url == "https://test.example.com:8443/api/v1/email/send"

    def test_email_send_markdown_url(self, monkeypatch):
        """Markdown 이메일 발송 엔드포인트 URL을 올바르게 생성한다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com:8443")
        monkeypatch.setenv("API_BEARER_TOKEN", "token")

        settings = Settings()

        assert (
            settings.email_send_markdown_url
            == "https://test.example.com:8443/api/v1/email/send_markdown"
        )

    def test_auth_header(self, monkeypatch):
        """Authorization 헤더를 올바르게 생성한다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com")
        monkeypatch.setenv("API_BEARER_TOKEN", "my-secret-token")

        settings = Settings()

        assert settings.auth_header == {"Authorization": "Bearer my-secret-token"}

    def test_recipient_mapping_comma_separated(self, monkeypatch):
        """쉼표 구분 파싱을 테스트한다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com")
        monkeypatch.setenv("API_BEARER_TOKEN", "token")
        monkeypatch.setenv("EMAIL_RECIPIENT_MAPPING", "홍길동:hong@test.com, 김철수:kim@test.com")

        settings = Settings()
        assert settings.recipient_mapping == {"홍길동": "hong@test.com", "김철수": "kim@test.com"}

    def test_recipient_mapping_json(self, monkeypatch):
        """JSON 데이터 파싱을 테스트한다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com")
        monkeypatch.setenv("API_BEARER_TOKEN", "token")
        monkeypatch.setenv("EMAIL_RECIPIENT_MAPPING", '{"홍길동": "hong@test.com"}')

        settings = Settings()
        assert settings.recipient_mapping == {"홍길동": "hong@test.com"}


class TestResponseSizeLimitSetting:
    """응답 크기 한도 설정 테스트."""

    def test_defaults_to_30k(self, monkeypatch):
        """MCP_MAX_RESPONSE_BYTES 미설정 시 기본값 30,000 바이트를 쓴다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com:8443")
        monkeypatch.setenv("API_BEARER_TOKEN", "test-token-123")
        monkeypatch.delenv(MAX_RESPONSE_BYTES_ENV, raising=False)

        assert Settings().max_response_bytes == DEFAULT_MAX_RESPONSE_BYTES

    def test_reads_limit_from_env(self, monkeypatch):
        """환경변수로 응답 크기 한도를 조정할 수 있다."""
        monkeypatch.setenv("API_BASE_URL", "https://test.example.com:8443")
        monkeypatch.setenv("API_BEARER_TOKEN", "test-token-123")
        monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "12345")

        assert Settings().max_response_bytes == 12345
