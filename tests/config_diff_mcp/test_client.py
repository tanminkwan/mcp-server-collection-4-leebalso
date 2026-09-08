"""DiffClient 테스트."""

from unittest.mock import patch

import httpx
import pytest
import respx

from config_diff_mcp.client import DiffClient
from config_diff_mcp.config import Settings, WAS_RESOURCE, WEB_RESOURCE


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("config_diff_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def settings(monkeypatch) -> Settings:
    monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    monkeypatch.delenv("API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("DIFF_DATE_PADDING_DAYS", raising=False)
    return Settings()


@pytest.fixture()
def client(settings) -> DiffClient:
    return DiffClient(settings)


WEB_LIST_URL = "https://app.mwm.local:20443/diff_data/web/list"
WAS_LIST_URL = "https://app.mwm.local:20443/diff_data/was/list"


class TestListDiffs:
    """DiffClient.list_diffs 테스트."""

    @respx.mock
    async def test_web_list_sends_query_params(self, client):
        """WEB 목록 조회 시 전달받은 쿼리 파라미터를 그대로 전송한다."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=[]))

        await client.list_diffs(
            WEB_RESOURCE,
            {"host_id": "paaaa11", "start_date": "2026-08-10", "end_date": "2026-08-12"},
        )

        request = route.calls.last.request
        assert dict(request.url.params) == {
            "host_id": "paaaa11",
            "start_date": "2026-08-10",
            "end_date": "2026-08-12",
        }

    @respx.mock
    async def test_was_list_sends_query_params(self, client):
        """WAS 목록 조회 시 domain_id 필터를 전송한다."""
        route = respx.get(WAS_LIST_URL).mock(return_value=httpx.Response(200, json=[]))

        await client.list_diffs(WAS_RESOURCE, {"domain_id": "PAAA_Domain"})

        assert dict(route.calls.last.request.url.params) == {"domain_id": "PAAA_Domain"}

    @respx.mock
    async def test_sends_authorization_header(self, client):
        """요청에 Bearer 인증 헤더를 포함한다."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=[]))

        await client.list_diffs(WEB_RESOURCE, {"host_id": "paaaa11"})

        assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"

    @respx.mock
    async def test_returns_parsed_json(self, client):
        """응답 JSON을 그대로 반환한다 (가공하지 않는다)."""
        payload = {
            "data": [{"id": 1, "host_id": "paaaa11", "create_on": "2026-08-11 10:00:00"}]
        }
        respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=payload))

        assert await client.list_diffs(WEB_RESOURCE, {"host_id": "paaaa11"}) == payload

    @respx.mock
    async def test_raises_on_http_error(self, client):
        """HTTP 오류 응답은 예외로 전파한다."""
        respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(500))

        with pytest.raises(httpx.HTTPStatusError):
            await client.list_diffs(WEB_RESOURCE, {"host_id": "paaaa11"})


class TestGetDiffDetail:
    """DiffClient.get_diff_detail 테스트."""

    @respx.mock
    async def test_web_detail_url_contains_record_id(self, client):
        """WEB 상세 조회 URL에 레코드 ID가 포함된다."""
        detail = {"host_id": "paaaa11", "new": "n", "old": "o", "unified_diff": "d"}
        route = respx.get("https://app.mwm.local:20443/diff_data/web/123").mock(
            return_value=httpx.Response(200, json=detail)
        )

        assert await client.get_diff_detail(WEB_RESOURCE, 123) == detail
        assert route.called

    @respx.mock
    async def test_was_detail_url_contains_record_id(self, client):
        """WAS 상세 조회 URL에 레코드 ID가 포함된다."""
        detail = {"domain_id": "PAAA_Domain", "new": "n", "old": "o", "unified_diff": "d"}
        route = respx.get("https://app.mwm.local:20443/diff_data/was/456").mock(
            return_value=httpx.Response(200, json=detail)
        )

        assert await client.get_diff_detail(WAS_RESOURCE, 456) == detail
        assert route.called

    @respx.mock
    async def test_raises_on_not_found(self, client):
        """404 응답은 예외로 전파한다 (서버가 메시지로 변환한다)."""
        respx.get("https://app.mwm.local:20443/diff_data/web/999").mock(
            return_value=httpx.Response(404)
        )

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_diff_detail(WEB_RESOURCE, 999)
