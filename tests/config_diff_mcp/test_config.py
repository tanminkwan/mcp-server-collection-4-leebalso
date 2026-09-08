"""config 모듈 테스트."""

from unittest.mock import patch

import pytest

from config_diff_mcp.config import (
    DEFAULT_DATE_PADDING_DAYS,
    Settings,
    WAS_RESOURCE,
    WEB_RESOURCE,
)


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("config_diff_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def _base_env(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    monkeypatch.delenv("API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("DIFF_DATE_PADDING_DAYS", raising=False)


class TestSettings:
    """Settings 클래스 테스트."""

    def test_load_from_env(self, _base_env):
        """필수 환경변수에서 설정값을 로드한다."""
        settings = Settings()

        assert settings.api_base_url == "https://app.mwm.local:20443"
        assert settings.api_bearer_token == "secret-token"

    def test_missing_base_url_raises(self, _base_env, monkeypatch):
        """API_BASE_URL 누락 시 에러를 발생시킨다."""
        monkeypatch.delenv("API_BASE_URL", raising=False)

        with pytest.raises(ValueError, match="API_BASE_URL"):
            Settings()

    def test_missing_bearer_token_raises(self, _base_env, monkeypatch):
        """API_BEARER_TOKEN 누락 시 에러를 발생시킨다."""
        monkeypatch.delenv("API_BEARER_TOKEN", raising=False)

        with pytest.raises(ValueError, match="API_BEARER_TOKEN"):
            Settings()

    def test_auth_header(self, _base_env):
        """Bearer Authorization 헤더를 생성한다."""
        settings = Settings()

        assert settings.auth_header == {"Authorization": "Bearer secret-token"}

    def test_ssl_verify_defaults_to_false(self, _base_env):
        """API_SSL_VERIFY 미설정 시 기본값은 False이다."""
        assert Settings().api_ssl_verify is False

    def test_ssl_verify_overridden_by_env(self, _base_env, monkeypatch):
        """API_SSL_VERIFY 환경변수로 SSL 검증을 켤 수 있다."""
        monkeypatch.setenv("API_SSL_VERIFY", "true")

        assert Settings().api_ssl_verify is True

    def test_timeout_defaults_to_60(self, _base_env):
        """API_TIMEOUT 미설정 시 기본값은 60이다."""
        assert Settings().api_timeout == 60

    def test_date_padding_days_defaults(self, _base_env):
        """DIFF_DATE_PADDING_DAYS 미설정 시 기본값을 사용한다."""
        assert Settings().date_padding_days == DEFAULT_DATE_PADDING_DAYS

    def test_date_padding_days_overridden_by_env(self, _base_env, monkeypatch):
        """DIFF_DATE_PADDING_DAYS 환경변수로 여유일수를 재정의할 수 있다."""
        monkeypatch.setenv("DIFF_DATE_PADDING_DAYS", "3")

        assert Settings().date_padding_days == 3

    def test_list_url_web(self, _base_env):
        """WEB 목록 조회 URL을 올바르게 생성한다."""
        settings = Settings()

        assert settings.list_url(WEB_RESOURCE) == (
            "https://app.mwm.local:20443/diff_data/web/list"
        )

    def test_list_url_was(self, _base_env):
        """WAS 목록 조회 URL을 올바르게 생성한다."""
        settings = Settings()

        assert settings.list_url(WAS_RESOURCE) == (
            "https://app.mwm.local:20443/diff_data/was/list"
        )

    def test_detail_url_web(self, _base_env):
        """WEB 상세 조회 URL에 레코드 ID를 채워 생성한다."""
        settings = Settings()

        assert settings.detail_url(WEB_RESOURCE, 123) == (
            "https://app.mwm.local:20443/diff_data/web/123"
        )

    def test_detail_url_was(self, _base_env):
        """WAS 상세 조회 URL에 레코드 ID를 채워 생성한다."""
        settings = Settings()

        assert settings.detail_url(WAS_RESOURCE, 456) == (
            "https://app.mwm.local:20443/diff_data/was/456"
        )


class TestResourceSpec:
    """리소스 정의(ResourceSpec) 테스트."""

    def test_web_filter_key_is_host_id(self):
        """WEB 목록 조회 필터 키는 host_id 이다."""
        assert WEB_RESOURCE.filter_key == "host_id"

    def test_was_filter_key_is_domain_id(self):
        """WAS 목록 조회 필터 키는 domain_id 이다."""
        assert WAS_RESOURCE.filter_key == "domain_id"

    def test_web_config_file_name(self):
        """WEB 설정 파일명은 http.m 이다."""
        assert WEB_RESOURCE.config_file_name == "http.m"

    def test_was_config_file_name(self):
        """WAS 설정 파일명은 domain.xml 이다."""
        assert WAS_RESOURCE.config_file_name == "domain.xml"

    def test_missing_filter_messages_guide_re_ask(self):
        """식별자 누락 메시지는 사용자에게 되묻도록 유도하는 문구를 포함한다."""
        assert "host_id" in WEB_RESOURCE.missing_filter_message
        assert "domain_id" in WAS_RESOURCE.missing_filter_message
