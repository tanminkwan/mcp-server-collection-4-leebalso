"""ExtractLogClient 테스트."""

from unittest.mock import patch

import httpx
import pytest
import respx

from extract_error_log_mcp.client import ExtractLogClient
from extract_error_log_mcp.config import (
    MDCONTENT_LIST_MAX,
    Settings,
)
from mcp_common.config import MAX_RESPONSE_BYTES_ENV


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("extract_error_log_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def settings(monkeypatch) -> Settings:
    monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    monkeypatch.delenv("API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv(MAX_RESPONSE_BYTES_ENV, raising=False)
    return Settings()


@pytest.fixture()
def client(settings) -> ExtractLogClient:
    return ExtractLogClient(settings)


EXTRACT_URL = "https://app.mwm.local:20443/api/v1/command_master/extract_log"
LIST_URL = "https://app.mwm.local:20443/api/v1/knowledge/mdcontent/list"
DETAIL_URL = "https://app.mwm.local:20443/api/v1/knowledge/mdcontent/7"

PAYLOAD = {
    "date": "20260914",
    "host_id": "pcbkaa11",
    "time_from": "090000",
    "time_to": "100000",
    "was_instance_id": "ONL_MS12",
}


class TestRequestExtractLog:
    """로그 추출 요청."""

    @respx.mock
    async def test_posts_payload_and_returns_json(self, client):
        route = respx.post(EXTRACT_URL).mock(
            return_value=httpx.Response(201, json={"command_id": "cmd-1"})
        )

        result = await client.request_extract_log(PAYLOAD)

        assert result == {"command_id": "cmd-1"}
        assert route.calls.last.request.read().decode() == httpx.Request(
            "POST", EXTRACT_URL, json=PAYLOAD
        ).read().decode()

    @respx.mock
    async def test_sends_bearer_token(self, client):
        route = respx.post(EXTRACT_URL).mock(
            return_value=httpx.Response(201, json={})
        )

        await client.request_extract_log(PAYLOAD)

        assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"

    @respx.mock
    async def test_raises_on_http_error(self, client):
        respx.post(EXTRACT_URL).mock(return_value=httpx.Response(500))

        with pytest.raises(httpx.HTTPStatusError):
            await client.request_extract_log(PAYLOAD)


class TestGetMdcontentList:
    """mdcontent 목록 조회."""

    @respx.mock
    async def test_queries_by_search_tags(self, client):
        route = respx.get(LIST_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"content_id": 7}]})
        )

        result = await client.get_mdcontent_list(search_tags="cmd-1")

        params = route.calls.last.request.url.params
        assert params["search_tags"] == "cmd-1"
        assert params["max"] == str(MDCONTENT_LIST_MAX)
        assert result == {"data": [{"content_id": 7}]}

    @respx.mock
    async def test_raises_on_http_error(self, client):
        respx.get(LIST_URL).mock(return_value=httpx.Response(404))

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_mdcontent_list(search_tags="cmd-1")


class TestGetMdcontent:
    """mdcontent 상세 조회."""

    @respx.mock
    async def test_fetches_by_content_id(self, client):
        route = respx.get(DETAIL_URL).mock(
            return_value=httpx.Response(200, json={"content_id": 7, "mdcontent": "# 로그"})
        )

        result = await client.get_mdcontent(7)

        assert result["mdcontent"] == "# 로그"
        assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"

    @respx.mock
    async def test_raises_on_http_error(self, client):
        respx.get(DETAIL_URL).mock(return_value=httpx.Response(500))

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_mdcontent(7)
