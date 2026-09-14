"""read_server_file_mcp 설정 모듈 테스트."""

from unittest.mock import patch

import pytest

from read_server_file_mcp.config import (
    AGENT_CONDITION_PARAM,
    AGENT_ID_COLUMN,
    AGENT_LOOKUP_OPERATOR,
    AGENT_TABLE,
    COMMAND_CREATE_PATH,
    COMMAND_RESULT_PATH,
    DEFAULT_RESULT_WAIT_SECONDS,
    DEFAULT_SSL_VERIFY,
    DEFAULT_TIMEOUT,
    HOST_ID_COLUMN,
    READ_FILE_COMMAND_TYPE_ID,
    Settings,
    build_agent_condition,
)


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("read_server_file_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def _base_env(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    monkeypatch.delenv("API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("READ_SERVER_FILE_RESULT_WAIT_SECONDS", raising=False)


class TestRequiredEnv:
    """필수 환경변수 검증."""

    def test_loads_required_values(self, _base_env):
        settings = Settings()

        assert settings.api_base_url == "https://app.mwm.local:20443"
        assert settings.api_bearer_token == "secret-token"

    def test_missing_base_url_raises(self, monkeypatch):
        monkeypatch.delenv("API_BASE_URL", raising=False)
        monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")

        with pytest.raises(ValueError, match="API_BASE_URL"):
            Settings()

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
        monkeypatch.delenv("API_BEARER_TOKEN", raising=False)

        with pytest.raises(ValueError, match="API_BEARER_TOKEN"):
            Settings()


class TestOptionalEnv:
    """선택 환경변수의 기본값과 재정의."""

    def test_defaults(self, _base_env):
        settings = Settings()

        assert settings.api_ssl_verify is DEFAULT_SSL_VERIFY
        assert settings.api_timeout == DEFAULT_TIMEOUT
        assert settings.result_wait_seconds == DEFAULT_RESULT_WAIT_SECONDS

    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes"])
    def test_ssl_verify_truthy(self, _base_env, monkeypatch, raw):
        monkeypatch.setenv("API_SSL_VERIFY", raw)

        assert Settings().api_ssl_verify is True

    @pytest.mark.parametrize("raw", ["false", "no", "0", "anything"])
    def test_ssl_verify_falsy(self, _base_env, monkeypatch, raw):
        monkeypatch.setenv("API_SSL_VERIFY", raw)

        assert Settings().api_ssl_verify is False

    def test_timeout_override(self, _base_env, monkeypatch):
        monkeypatch.setenv("API_TIMEOUT", "5")

        assert Settings().api_timeout == 5

    def test_result_wait_seconds_override(self, _base_env, monkeypatch):
        monkeypatch.setenv("READ_SERVER_FILE_RESULT_WAIT_SECONDS", "45")

        assert Settings().result_wait_seconds == 45


class TestDerivedValues:
    """URL 및 인증 헤더 생성."""

    def test_create_url(self, _base_env):
        assert Settings().create_url == (
            f"https://app.mwm.local:20443{COMMAND_CREATE_PATH}"
        )

    def test_result_url(self, _base_env):
        assert Settings().result_url == (
            f"https://app.mwm.local:20443{COMMAND_RESULT_PATH}"
        )

    def test_agent_lookup_url_targets_agent_id_column(self, _base_env):
        """에이전트 조회 URL은 <테이블>.<컬럼> 형식을 사용한다."""
        url = Settings().agent_lookup_url

        assert url.startswith("https://app.mwm.local:20443")
        assert url.endswith(f"{AGENT_TABLE}.{AGENT_ID_COLUMN}")

    def test_auth_header(self, _base_env):
        assert Settings().auth_header == {"Authorization": "Bearer secret-token"}


class TestBuildAgentCondition:
    """host_id 조건 JSON 생성."""

    def test_condition_shape(self):
        import json

        condition = build_agent_condition("pcbkaa11")

        assert json.loads(condition) == {
            "column": HOST_ID_COLUMN,
            "operator": AGENT_LOOKUP_OPERATOR,
            "value": "pcbkaa11",
        }

    def test_condition_param_name(self):
        assert AGENT_CONDITION_PARAM == "condition"


class TestCommandType:
    """파일 읽기 명령 타입 상수."""

    def test_read_file_command_type(self):
        """절대 경로를 지정해 읽는 범용 명령 타입을 사용한다."""
        assert READ_FILE_COMMAND_TYPE_ID == "COMMON.READFILE"
