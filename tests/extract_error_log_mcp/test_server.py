"""extract_error_log_mcp 응답 크기 제한 테스트."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from extract_error_log_mcp.server import create_server
from mcp_common.config import MAX_RESPONSE_BYTES_ENV
from mcp_common.response_limit import ResponseTooLargeError


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


LIST_URL = "https://app.mwm.local:20443/api/v1/knowledge/mdcontent/list"
DETAIL_URL = "https://app.mwm.local:20443/api/v1/knowledge/mdcontent/1"


def _fn(mcp, name):
    return mcp._tool_manager._tools[name].fn


class TestResponseSizeLimit:
    """응답 크기 제한 테스트."""

    @respx.mock
    async def test_oversized_mdcontent_raises_error(self, monkeypatch, _env):
        """추출된 로그 문서가 한도를 넘으면 '너무 크다'는 오류로 반환된다."""
        monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "500")
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"content_id": 1}]})
        )
        respx.get(DETAIL_URL).mock(
            return_value=httpx.Response(
                200, json={"content_id": 1, "mdcontent": "에러 로그\n" * 2000}
            )
        )

        mcp = create_server()
        with pytest.raises(ResponseTooLargeError) as exc_info:
            await _fn(mcp, "get_extracted_log")(command_id="cmd-1")
        assert "너무 커서" in str(exc_info.value)

    @respx.mock
    async def test_mdcontent_within_limit_passes_through(self, _env):
        """기본 한도(30KB) 이내 응답은 그대로 반환된다."""
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"content_id": 1}]})
        )
        respx.get(DETAIL_URL).mock(
            return_value=httpx.Response(200, json={"content_id": 1, "mdcontent": "짧은 로그"})
        )

        mcp = create_server()
        result = json.loads(await _fn(mcp, "get_extracted_log")(command_id="cmd-1"))

        assert result["mdcontent"] == "짧은 로그"
