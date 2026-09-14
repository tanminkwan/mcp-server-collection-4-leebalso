"""config 모듈 테스트."""

from unittest.mock import patch

import pytest

from error_rag_mcp.config import Settings
from mcp_common.config import DEFAULT_MAX_RESPONSE_BYTES, MAX_RESPONSE_BYTES_ENV


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("error_rag_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def _base_env(monkeypatch):
    monkeypatch.setenv("RAG_API_BASE_URL", "http://localhost:28000")
    monkeypatch.setenv("RAG_COLLECTION_NAME", "error_rag_test")
    monkeypatch.setenv("RAG_DOMAIN_ID", "6")
    monkeypatch.delenv("RAG_API_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("RAG_API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("RAG_API_TIMEOUT", raising=False)
    monkeypatch.delenv("RAG_VECTOR_SEARCH_LIMIT", raising=False)
    monkeypatch.delenv("RAG_TEXT_MATCHING_LIMIT", raising=False)
    monkeypatch.delenv("RAG_SOURCE", raising=False)


class TestSettings:
    """Settings 클래스 테스트."""

    def test_load_from_env(self, _base_env):
        """필수 환경변수에서 설정값을 로드한다."""
        settings = Settings()

        assert settings.api_base_url == "http://localhost:28000"
        assert settings.collection_name == "error_rag_test"
        assert settings.domain_id == 6

    def test_domain_id_parsed_as_int(self, _base_env, monkeypatch):
        """domain_id는 정수로 파싱된다."""
        monkeypatch.setenv("RAG_DOMAIN_ID", "42")

        settings = Settings()

        assert settings.domain_id == 42
        assert isinstance(settings.domain_id, int)

    def test_missing_base_url_raises(self, _base_env, monkeypatch):
        """RAG_API_BASE_URL 누락 시 에러를 발생시킨다."""
        monkeypatch.delenv("RAG_API_BASE_URL", raising=False)

        with pytest.raises(ValueError, match="RAG_API_BASE_URL"):
            Settings()

    def test_missing_collection_name_raises(self, _base_env, monkeypatch):
        """RAG_COLLECTION_NAME 누락 시 에러를 발생시킨다."""
        monkeypatch.delenv("RAG_COLLECTION_NAME", raising=False)

        with pytest.raises(ValueError, match="RAG_COLLECTION_NAME"):
            Settings()

    def test_missing_domain_id_raises(self, _base_env, monkeypatch):
        """RAG_DOMAIN_ID 누락 시 에러를 발생시킨다."""
        monkeypatch.delenv("RAG_DOMAIN_ID", raising=False)

        with pytest.raises(ValueError, match="RAG_DOMAIN_ID"):
            Settings()

    def test_bearer_token_defaults_to_none(self, _base_env):
        """RAG_API_BEARER_TOKEN 미설정 시 None이다."""
        settings = Settings()

        assert settings.api_bearer_token is None

    def test_auth_header_empty_without_token(self, _base_env):
        """토큰이 없으면 Authorization 헤더를 생략한다."""
        settings = Settings()

        assert settings.auth_header == {}

    def test_auth_header_with_token(self, _base_env, monkeypatch):
        """토큰이 있으면 Bearer Authorization 헤더를 생성한다."""
        monkeypatch.setenv("RAG_API_BEARER_TOKEN", "secret-token")

        settings = Settings()

        assert settings.auth_header == {"Authorization": "Bearer secret-token"}

    def test_ssl_verify_defaults_to_false(self, _base_env):
        """RAG_API_SSL_VERIFY 미설정 시 기본값은 False이다."""
        settings = Settings()

        assert settings.api_ssl_verify is False

    def test_timeout_defaults_to_60(self, _base_env):
        """RAG_API_TIMEOUT 미설정 시 기본값은 60이다."""
        settings = Settings()

        assert settings.api_timeout == 60

    def test_vector_search_limit_defaults_to_3(self, _base_env):
        """RAG_VECTOR_SEARCH_LIMIT 미설정 시 기본값은 3이다."""
        settings = Settings()

        assert settings.vector_search_limit == 3

    def test_text_matching_limit_defaults_to_2(self, _base_env):
        """RAG_TEXT_MATCHING_LIMIT 미설정 시 기본값은 2이다."""
        settings = Settings()

        assert settings.text_matching_limit == 2

    def test_source_defaults_to_error_resolution_report(self, _base_env):
        """RAG_SOURCE 미설정 시 기본값은 'error-resolution-report'이다."""
        settings = Settings()

        assert settings.source == "error-resolution-report"

    def test_source_overridden_by_env(self, _base_env, monkeypatch):
        """RAG_SOURCE 환경변수로 source 값을 재정의할 수 있다."""
        monkeypatch.setenv("RAG_SOURCE", "custom-source")

        settings = Settings()

        assert settings.source == "custom-source"

    def test_search_url(self, _base_env):
        """검색 엔드포인트 URL을 올바르게 생성한다."""
        settings = Settings()

        assert settings.search_url == "http://localhost:28000/api/rag/search"

    def test_knowledge_url(self, _base_env):
        """등록 엔드포인트 URL을 올바르게 생성한다."""
        settings = Settings()

        assert settings.knowledge_url == "http://localhost:28000/api/rag/knowledge"


class TestResponseSizeLimitSetting:
    """응답 크기 한도 설정 테스트."""

    def test_defaults_to_30k(self, monkeypatch):
        """MCP_MAX_RESPONSE_BYTES 미설정 시 기본값 30,000 바이트를 쓴다."""
        monkeypatch.setenv("RAG_API_BASE_URL", "http://localhost:28000")
        monkeypatch.setenv("RAG_COLLECTION_NAME", "c")
        monkeypatch.setenv("RAG_DOMAIN_ID", "6")
        monkeypatch.delenv(MAX_RESPONSE_BYTES_ENV, raising=False)

        assert Settings().max_response_bytes == DEFAULT_MAX_RESPONSE_BYTES

    def test_reads_limit_from_env(self, monkeypatch):
        """환경변수로 응답 크기 한도를 조정할 수 있다."""
        monkeypatch.setenv("RAG_API_BASE_URL", "http://localhost:28000")
        monkeypatch.setenv("RAG_COLLECTION_NAME", "c")
        monkeypatch.setenv("RAG_DOMAIN_ID", "6")
        monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "12345")

        assert Settings().max_response_bytes == 12345
