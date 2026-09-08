"""MCP 서버 테스트."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from config_diff_mcp.config import (
    NOT_FOUND_MESSAGE,
    WAS_RESOURCE,
    WEB_RESOURCE,
)
from config_diff_mcp.server import create_diff_client, create_server


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("config_diff_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def _env(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    monkeypatch.delenv("API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("DIFF_DATE_PADDING_DAYS", raising=False)


@pytest.fixture()
def mcp(_env):
    return create_server()


WEB_LIST_URL = "https://app.mwm.local:20443/diff_data/web/list"
WAS_LIST_URL = "https://app.mwm.local:20443/diff_data/was/list"
_JSON_HEADERS = {"Content-Type": "application/json"}


def _list(records):
    """실제 API의 목록 응답 형태({"data": [...]})로 감싼다."""
    return {"data": records}


def _tool(mcp, name):
    return mcp._tool_manager._tools[name]


def _fn(mcp, name):
    return _tool(mcp, name).fn


def _web_detail(**overrides):
    detail = {
        "host_id": "paaaa11",
        "port": 8080,
        "create_on": "2026-08-11 14:23:01",
        "new": "현재 http.m 전문",
        "old": "이전 http.m 전문",
        "unified_diff": "-Timeout 30\n+Timeout 60",
    }
    detail.update(overrides)
    return detail


def _was_detail(**overrides):
    detail = {
        "domain_id": "PAAA_Domain",
        "create_on": "2026-08-11 14:23:01",
        "new": "현재 domain.xml 전문",
        "old": "이전 domain.xml 전문",
        "unified_diff": "-<max-threads>10</max-threads>\n+<max-threads>50</max-threads>",
    }
    detail.update(overrides)
    return detail


class TestCreateServer:
    """서버 생성 테스트."""

    def test_server_name(self, mcp):
        """서버 이름이 올바르게 설정된다."""
        assert mcp.name == "config-diff-mcp"

    def test_server_has_tools(self, mcp):
        """WAS/WEB 변경 이력 조회 도구가 등록되어 있다."""
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "get_diff_was" in tool_names
        assert "get_diff_web" in tool_names

    def test_create_diff_client(self, _env):
        """Settings 를 로드해 DiffClient 를 생성한다."""
        from config_diff_mcp.client import DiffClient

        assert isinstance(create_diff_client(), DiffClient)


class TestToolDescriptionAliases:
    """도구 설명에 설정 파일명 별칭이 노출되는지 테스트 (AI Agent 도구 선택 근거)."""

    def test_web_tool_description_mentions_http_m(self, mcp):
        """get_diff_web 설명에 http.m 이 포함된다."""
        assert WEB_RESOURCE.config_file_name in _tool(mcp, "get_diff_web").description

    def test_was_tool_description_mentions_domain_xml(self, mcp):
        """get_diff_was 설명에 domain.xml 이 포함된다."""
        assert WAS_RESOURCE.config_file_name in _tool(mcp, "get_diff_was").description

    def test_instructions_mention_both_config_file_names(self, mcp):
        """서버 instructions에 두 설정 파일명이 모두 포함된다."""
        assert WEB_RESOURCE.config_file_name in mcp.instructions
        assert WAS_RESOURCE.config_file_name in mcp.instructions


class TestMissingIdentifier:
    """대상 식별자 누락 시 되묻기 테스트 (설계서 3.5절)."""

    @respx.mock
    async def test_web_missing_host_id_does_not_call_api(self, mcp):
        """host_id 가 없으면 API를 호출하지 않고 되묻기 메시지를 반환한다."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        result = json.loads(await _fn(mcp, "get_diff_web")(host_id=""))

        assert result["found"] is False
        assert result["message"] == WEB_RESOURCE.missing_filter_message
        assert route.call_count == 0

    @respx.mock
    async def test_web_blank_host_id_does_not_call_api(self, mcp):
        """공백만 있는 host_id 도 누락으로 취급한다."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        result = json.loads(await _fn(mcp, "get_diff_web")(host_id="   "))

        assert result["message"] == WEB_RESOURCE.missing_filter_message
        assert route.call_count == 0

    @respx.mock
    async def test_was_missing_domain_id_does_not_call_api(self, mcp):
        """domain_id 가 없으면 API를 호출하지 않고 되묻기 메시지를 반환한다."""
        route = respx.get(WAS_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        result = json.loads(await _fn(mcp, "get_diff_was")(domain_id=""))

        assert result["found"] is False
        assert result["message"] == WAS_RESOURCE.missing_filter_message
        assert route.call_count == 0


class TestResultCountBranching:
    """목록 건수별 분기 테스트 (설계서 3.1절)."""

    @respx.mock
    async def test_zero_records_returns_not_found(self, mcp):
        """0건이면 '존재하지 않습니다'를 반환하고 상세를 조회하지 않는다."""
        respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        result = json.loads(await _fn(mcp, "get_diff_web")(host_id="paaaa11"))

        assert result == {
            "found": False,
            "total_count": 0,
            "message": NOT_FOUND_MESSAGE,
        }

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(200, content=b"null", headers=_JSON_HEADERS),
            httpx.Response(200, json={}),
        ],
        ids=["null", "no-data-key"],
    )
    @respx.mock
    async def test_non_list_response_treated_as_zero(self, mcp, response):
        """null 이거나 data 키가 없는 응답도 0건으로 취급한다 (방어적 처리)."""
        respx.get(WEB_LIST_URL).mock(return_value=response)

        result = json.loads(await _fn(mcp, "get_diff_web")(host_id="paaaa11"))

        assert result["found"] is False
        assert result["message"] == NOT_FOUND_MESSAGE

    @respx.mock
    async def test_bare_array_response_is_supported(self, mcp):
        """OpenAPI 스펙대로 봉투 없이 배열로 응답해도 동일하게 처리한다.

        실제 API는 {"data": [...]} 형태로 응답하지만 스펙에는 배열로 선언되어 있어
        두 형태를 모두 받아들인다.
        """
        respx.get(WAS_LIST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[{"id": 7, "domain_id": "PICI_Domain", "create_on": "2026-02-23 14:40:00"}],
            )
        )
        respx.get("https://app.mwm.local:20443/diff_data/was/7").mock(
            return_value=httpx.Response(200, json=_was_detail())
        )

        result = json.loads(await _fn(mcp, "get_diff_was")(domain_id="PICI_Domain"))

        assert result["found"] is True
        assert result["diff"]["id"] == 7

    @respx.mock
    async def test_single_record_returns_detail_without_notice(self, mcp):
        """1건이면 notice 없이 그 건의 상세를 반환한다."""
        respx.get(WEB_LIST_URL).mock(
            return_value=httpx.Response(200, json=_list([{"id": 123, "host_id": "paaaa11", "create_on": "2026-08-11 14:23:01"}]),
            )
        )
        respx.get("https://app.mwm.local:20443/diff_data/web/123").mock(
            return_value=httpx.Response(200, json=_web_detail())
        )

        result = json.loads(await _fn(mcp, "get_diff_web")(host_id="paaaa11"))

        assert result["found"] is True
        assert result["total_count"] == 1
        assert result["notice"] is None
        assert result["diff"]["id"] == 123
        assert result["diff"]["unified_diff"] == "-Timeout 30\n+Timeout 60"

    @respx.mock
    async def test_multiple_records_returns_latest_with_notice(self, mcp):
        """2건 이상이면 최신 1건만 반환하고 전체 건수/일시 안내를 덧붙인다."""
        respx.get(WEB_LIST_URL).mock(
            return_value=httpx.Response(200, json=_list([
                    {"id": 1, "host_id": "paaaa11", "create_on": "2026-08-09 09:00:00"},
                    {"id": 3, "host_id": "paaaa11", "create_on": "2026-08-11 14:23:01"},
                    {"id": 2, "host_id": "paaaa11", "create_on": "2026-08-10 11:00:00"},
                ]),
            )
        )
        route = respx.get("https://app.mwm.local:20443/diff_data/web/3").mock(
            return_value=httpx.Response(200, json=_web_detail())
        )

        result = json.loads(await _fn(mcp, "get_diff_web")(host_id="paaaa11"))

        assert route.called
        assert result["total_count"] == 3
        assert result["diff"]["id"] == 3
        assert "3건" in result["notice"]
        assert "2026-08-11 14:23:01" in result["notice"]

    @respx.mock
    async def test_falls_back_to_id_when_create_on_unparseable(self, mcp):
        """create_on 파싱이 불가능하면 id 내림차순으로 최신 건을 고른다."""
        respx.get(WAS_LIST_URL).mock(
            return_value=httpx.Response(200, json=_list([
                    {"id": 7, "domain_id": "PAAA_Domain", "create_on": "알 수 없음"},
                    {"id": 9, "domain_id": "PAAA_Domain", "create_on": "알 수 없음"},
                ]),
            )
        )
        route = respx.get("https://app.mwm.local:20443/diff_data/was/9").mock(
            return_value=httpx.Response(200, json=_was_detail())
        )

        result = json.loads(await _fn(mcp, "get_diff_was")(domain_id="PAAA_Domain"))

        assert route.called
        assert result["diff"]["id"] == 9


    @respx.mock
    async def test_missing_create_on_and_non_numeric_id_do_not_raise(self, mcp):
        """create_on이 없거나 id가 숫자가 아니어도 예외 없이 최신 건을 선택한다."""
        respx.get(WAS_LIST_URL).mock(
            return_value=httpx.Response(200, json=_list([
                    {"id": "unknown", "domain_id": "PAAA_Domain", "create_on": None},
                    {"id": 5, "domain_id": "PAAA_Domain", "create_on": None},
                ]),
            )
        )
        route = respx.get("https://app.mwm.local:20443/diff_data/was/5").mock(
            return_value=httpx.Response(200, json=_was_detail())
        )

        result = json.loads(await _fn(mcp, "get_diff_was")(domain_id="PAAA_Domain"))

        assert route.called
        assert result["found"] is True
        assert result["diff"]["id"] == 5


class TestOldFieldRemoval:
    """상세 응답 old 필드 제거 테스트 (설계서 5.3절)."""

    @respx.mock
    async def test_web_detail_excludes_old(self, mcp):
        """WEB 상세 응답에서 old(이전 설정 전문)를 제거한다."""
        respx.get(WEB_LIST_URL).mock(
            return_value=httpx.Response(200, json=_list([{"id": 1, "host_id": "paaaa11", "create_on": "2026-08-11 14:23:01"}])
            )
        )
        respx.get("https://app.mwm.local:20443/diff_data/web/1").mock(
            return_value=httpx.Response(200, json=_web_detail())
        )

        result = json.loads(await _fn(mcp, "get_diff_web")(host_id="paaaa11"))

        assert "old" not in result["diff"]
        assert result["diff"]["new"] == "현재 http.m 전문"

    @respx.mock
    async def test_was_detail_excludes_old(self, mcp):
        """WAS 상세 응답에서 old(이전 설정 전문)를 제거한다."""
        respx.get(WAS_LIST_URL).mock(
            return_value=httpx.Response(200, json=_list([{"id": 5, "domain_id": "PAAA_Domain", "create_on": "2026-08-11 14:23:01"}]),
            )
        )
        respx.get("https://app.mwm.local:20443/diff_data/was/5").mock(
            return_value=httpx.Response(200, json=_was_detail())
        )

        result = json.loads(await _fn(mcp, "get_diff_was")(domain_id="PAAA_Domain"))

        assert "old" not in result["diff"]
        assert result["diff"]["domain_id"] == "PAAA_Domain"


class TestDateRangeNormalization:
    """날짜 구간 정규화 테스트 (설계서 4.2절)."""

    @respx.mock
    async def test_no_dates_sends_no_date_params(self, mcp):
        """날짜 미지정 시 날짜 파라미터를 보내지 않는다 (API가 최근 1건 반환)."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        await _fn(mcp, "get_diff_web")(host_id="paaaa11")

        params = dict(route.calls.last.request.url.params)
        assert params == {"host_id": "paaaa11"}

    @respx.mock
    async def test_start_date_only_is_padded(self, mcp):
        """시작일만 주면 단일 일자로 보고 앞뒤 1일씩 확장한다."""
        route = respx.get(WAS_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        await _fn(mcp, "get_diff_was")(domain_id="PAAA_Domain", start_date="2026-08-11")

        params = dict(route.calls.last.request.url.params)
        assert params["start_date"] == "2026-08-10"
        assert params["end_date"] == "2026-08-12"

    @respx.mock
    async def test_end_date_only_is_padded(self, mcp):
        """종료일만 주어도 단일 일자로 보고 앞뒤 1일씩 확장한다."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        await _fn(mcp, "get_diff_web")(host_id="paaaa11", end_date="2026-08-11")

        params = dict(route.calls.last.request.url.params)
        assert params["start_date"] == "2026-08-10"
        assert params["end_date"] == "2026-08-12"

    @respx.mock
    async def test_same_start_and_end_is_padded(self, mcp):
        """시작일과 종료일이 같으면 단일 일자로 보고 확장한다."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        await _fn(mcp, "get_diff_web")(
            host_id="paaaa11", start_date="2026-08-11", end_date="2026-08-11"
        )

        params = dict(route.calls.last.request.url.params)
        assert params["start_date"] == "2026-08-10"
        assert params["end_date"] == "2026-08-12"

    @respx.mock
    async def test_explicit_range_is_used_as_is(self, mcp):
        """명시적 구간(시작일 != 종료일)은 확장하지 않고 그대로 사용한다."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        await _fn(mcp, "get_diff_web")(
            host_id="paaaa11", start_date="2026-08-01", end_date="2026-08-31"
        )

        params = dict(route.calls.last.request.url.params)
        assert params["start_date"] == "2026-08-01"
        assert params["end_date"] == "2026-08-31"

    @respx.mock
    async def test_padding_days_configurable(self, mcp, monkeypatch):
        """여유일수는 DIFF_DATE_PADDING_DAYS 환경변수로 조정된다."""
        monkeypatch.setenv("DIFF_DATE_PADDING_DAYS", "3")
        configured = create_server()
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        await _fn(configured, "get_diff_web")(host_id="paaaa11", start_date="2026-08-11")

        params = dict(route.calls.last.request.url.params)
        assert params["start_date"] == "2026-08-08"
        assert params["end_date"] == "2026-08-14"

    @respx.mock
    async def test_invalid_date_format_does_not_call_api(self, mcp):
        """날짜 형식이 잘못되면 API를 호출하지 않고 오류 메시지를 반환한다."""
        route = respx.get(WEB_LIST_URL).mock(return_value=httpx.Response(200, json=_list([])))

        result = json.loads(
            await _fn(mcp, "get_diff_web")(host_id="paaaa11", start_date="8월 11일")
        )

        assert result["found"] is False
        assert result["message"].startswith("날짜는 YYYY-MM-DD")
        assert "8월 11일" in result["message"]
        assert route.call_count == 0


class TestErrorHandling:
    """오류 응답 테스트 (설계서 6.4절)."""

    @respx.mock
    async def test_detail_not_found_returns_message(self, mcp):
        """상세 조회 404는 예외 대신 안내 메시지로 변환한다."""
        respx.get(WEB_LIST_URL).mock(
            return_value=httpx.Response(200, json=_list([{"id": 77, "host_id": "paaaa11", "create_on": "2026-08-11 14:23:01"}])
            )
        )
        respx.get("https://app.mwm.local:20443/diff_data/web/77").mock(
            return_value=httpx.Response(404)
        )

        result = json.loads(await _fn(mcp, "get_diff_web")(host_id="paaaa11"))

        assert result["found"] is False
        assert "77" in result["message"]

    @respx.mock
    async def test_http_error_returns_message(self, mcp):
        """HTTP 오류는 예외를 던지지 않고 오류 응답 구조로 변환한다."""
        respx.get(WAS_LIST_URL).mock(return_value=httpx.Response(500))

        result = json.loads(await _fn(mcp, "get_diff_was")(domain_id="PAAA_Domain"))

        assert result["found"] is False
        assert result["total_count"] == 0
        assert result["message"]


class TestMain:
    """엔트리포인트 테스트."""

    def test_main_runs_stdio_server(self, _env):
        """main()은 stdio 전송 방식으로 서버를 실행한다."""
        from config_diff_mcp import server as server_module

        with patch.object(server_module, "create_server") as create:
            server_module.main()

        create.return_value.run.assert_called_once_with(transport="stdio")
