"""extract_error_log_mcp MCP 서버 테스트."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from extract_error_log_mcp.config import (
    INVALID_DATE_MESSAGE,
    INVALID_TIME_MESSAGE,
    INVALID_TIME_ORDER_MESSAGE,
    INVALID_WAS_INSTANCE_MESSAGE,
    MDCONTENT_NOT_FOUND_MESSAGE_TEMPLATE,
    NO_CONTENT_ID_MESSAGE_TEMPLATE,
    REQUEST_FAILED_MESSAGE_TEMPLATE,
    RESULT_FAILED_MESSAGE_TEMPLATE,
)
from extract_error_log_mcp.server import create_client, create_server
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


@pytest.fixture()
def mcp(_env):
    return create_server()


EXTRACT_URL = "https://app.mwm.local:20443/api/v1/command_master/extract_log"
LIST_URL = "https://app.mwm.local:20443/api/v1/knowledge/mdcontent/list"
DETAIL_URL = "https://app.mwm.local:20443/api/v1/knowledge/mdcontent/7"

VALID_ARGS = {
    "date": "20260914",
    "host_id": "pcbkaa11",
    "time_from": "090000",
    "time_to": "100000",
    "was_instance_id": "ONL_MS12",
}


def _tool(mcp, name):
    return mcp._tool_manager._tools[name]


def _fn(mcp, name):
    return _tool(mcp, name).fn


class TestToolRegistration:
    """서버 생성 및 도구 등록."""

    def test_server_name(self, mcp):
        assert mcp.name == "extract-error-log-mcp"

    def test_both_tools_registered(self, mcp):
        assert "request_extract_log" in mcp._tool_manager._tools
        assert "get_extracted_log" in mcp._tool_manager._tools

    def test_request_tool_requires_all_five_arguments(self, mcp):
        """응답 크기 가드로 감싸도 도구 스키마는 그대로 유지된다."""
        schema = _tool(mcp, "request_extract_log").parameters

        assert set(schema["required"]) == {
            "date",
            "host_id",
            "time_from",
            "time_to",
            "was_instance_id",
        }

    def test_result_tool_requires_command_id(self, mcp):
        assert _tool(mcp, "get_extracted_log").parameters["required"] == ["command_id"]

    def test_create_client_builds_client(self, _env):
        from extract_error_log_mcp.client import ExtractLogClient

        assert isinstance(create_client(), ExtractLogClient)


class TestRequestExtractLogValidation:
    """입력 검증 — 위반 시 API를 호출하지 않는다."""

    @respx.mock
    @pytest.mark.parametrize("date", ["2026914", "202609141", "abcdefgh", ""])
    async def test_rejects_malformed_date(self, mcp, date):
        route = respx.post(EXTRACT_URL)

        result = await _fn(mcp, "request_extract_log")(**{**VALID_ARGS, "date": date})

        assert result == INVALID_DATE_MESSAGE
        assert not route.called

    @respx.mock
    @pytest.mark.parametrize("field", ["time_from", "time_to"])
    async def test_rejects_malformed_time(self, mcp, field):
        route = respx.post(EXTRACT_URL)

        result = await _fn(mcp, "request_extract_log")(**{**VALID_ARGS, field: "9000"})

        assert result == INVALID_TIME_MESSAGE
        assert not route.called

    @respx.mock
    @pytest.mark.parametrize(
        ("time_from", "time_to"), [("100000", "090000"), ("090000", "090000")]
    )
    async def test_rejects_non_increasing_time_range(self, mcp, time_from, time_to):
        """time_from 은 time_to 보다 반드시 작아야 한다 (같아도 거부)."""
        route = respx.post(EXTRACT_URL)

        result = await _fn(mcp, "request_extract_log")(
            **{**VALID_ARGS, "time_from": time_from, "time_to": time_to}
        )

        assert result == INVALID_TIME_ORDER_MESSAGE
        assert not route.called

    @respx.mock
    async def test_rejects_was_instance_without_ms_token(self, mcp):
        route = respx.post(EXTRACT_URL)

        result = await _fn(mcp, "request_extract_log")(
            **{**VALID_ARGS, "was_instance_id": "ONL12"}
        )

        assert result == INVALID_WAS_INSTANCE_MESSAGE
        assert not route.called


class TestRequestExtractLogSuccess:
    """로그 추출 요청 성공/실패 경로."""

    @respx.mock
    async def test_returns_api_response_as_json(self, mcp):
        respx.post(EXTRACT_URL).mock(
            return_value=httpx.Response(201, json={"command_id": "cmd-1"})
        )

        result = json.loads(await _fn(mcp, "request_extract_log")(**VALID_ARGS))

        assert result["command_id"] == "cmd-1"

    @respx.mock
    async def test_sends_all_arguments_in_payload(self, mcp):
        route = respx.post(EXTRACT_URL).mock(
            return_value=httpx.Response(201, json={"command_id": "cmd-1"})
        )

        await _fn(mcp, "request_extract_log")(**VALID_ARGS)

        assert json.loads(route.calls.last.request.read()) == VALID_ARGS

    @respx.mock
    async def test_api_error_returns_message(self, mcp):
        respx.post(EXTRACT_URL).mock(return_value=httpx.Response(500))

        result = await _fn(mcp, "request_extract_log")(**VALID_ARGS)

        assert result.startswith(REQUEST_FAILED_MESSAGE_TEMPLATE.format(error=""))


class TestGetExtractedLog:
    """추출 결과 조회."""

    @respx.mock
    async def test_returns_mdcontent_detail(self, mcp):
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"content_id": 7}]})
        )
        respx.get(DETAIL_URL).mock(
            return_value=httpx.Response(200, json={"content_id": 7, "mdcontent": "# 로그"})
        )

        result = json.loads(await _fn(mcp, "get_extracted_log")(command_id="cmd-1"))

        assert result["mdcontent"] == "# 로그"

    @respx.mock
    async def test_looks_up_by_command_id(self, mcp):
        route = respx.get(LIST_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"content_id": 7}]})
        )
        respx.get(DETAIL_URL).mock(
            return_value=httpx.Response(200, json={"content_id": 7})
        )

        await _fn(mcp, "get_extracted_log")(command_id="cmd-1")

        assert route.calls.last.request.url.params["search_tags"] == "cmd-1"

    @respx.mock
    async def test_empty_list_reports_still_generating(self, mcp):
        """결과가 아직 없으면 생성 중일 수 있다고 안내한다."""
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json={"data": []}))

        result = await _fn(mcp, "get_extracted_log")(command_id="cmd-1")

        assert result == MDCONTENT_NOT_FOUND_MESSAGE_TEMPLATE.format(command_id="cmd-1")

    @respx.mock
    async def test_missing_data_key_reports_still_generating(self, mcp):
        respx.get(LIST_URL).mock(return_value=httpx.Response(200, json={}))

        result = await _fn(mcp, "get_extracted_log")(command_id="cmd-1")

        assert result == MDCONTENT_NOT_FOUND_MESSAGE_TEMPLATE.format(command_id="cmd-1")

    @respx.mock
    async def test_item_without_content_id_reports_response(self, mcp):
        """목록은 있는데 content_id 가 없으면 원본 응답을 그대로 실어 알린다."""
        first_item = {"title": "로그", "content_id": None}
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(200, json={"data": [first_item]})
        )

        result = await _fn(mcp, "get_extracted_log")(command_id="cmd-1")

        assert result == NO_CONTENT_ID_MESSAGE_TEMPLATE.format(
            response=json.dumps(first_item, ensure_ascii=False)
        )

    @respx.mock
    async def test_list_api_error_returns_message(self, mcp):
        respx.get(LIST_URL).mock(return_value=httpx.Response(500))

        result = await _fn(mcp, "get_extracted_log")(command_id="cmd-1")

        assert result.startswith(RESULT_FAILED_MESSAGE_TEMPLATE.format(error=""))

    @respx.mock
    async def test_detail_api_error_returns_message(self, mcp):
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"content_id": 7}]})
        )
        respx.get(DETAIL_URL).mock(return_value=httpx.Response(404))

        result = await _fn(mcp, "get_extracted_log")(command_id="cmd-1")

        assert result.startswith(RESULT_FAILED_MESSAGE_TEMPLATE.format(error=""))


class TestMain:
    """엔트리포인트."""

    def test_main_runs_stdio(self, _env):
        from extract_error_log_mcp import server as server_module

        with patch.object(server_module, "create_server") as create:
            server_module.main()

        create.return_value.run.assert_called_once_with(transport="stdio")


class TestResponseSizeLimit:
    """응답 크기 제한 테스트."""

    @respx.mock
    async def test_oversized_mdcontent_raises_error(self, monkeypatch, _env):
        """추출된 로그 문서가 한도를 넘으면 '너무 크다'는 오류로 반환된다."""
        monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "500")
        respx.get(LIST_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"content_id": 7}]})
        )
        respx.get(DETAIL_URL).mock(
            return_value=httpx.Response(
                200, json={"content_id": 7, "mdcontent": "에러 로그\n" * 2000}
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
            return_value=httpx.Response(200, json={"data": [{"content_id": 7}]})
        )
        respx.get(DETAIL_URL).mock(
            return_value=httpx.Response(200, json={"content_id": 7, "mdcontent": "짧은 로그"})
        )

        mcp = create_server()
        result = json.loads(await _fn(mcp, "get_extracted_log")(command_id="cmd-1"))

        assert result["mdcontent"] == "짧은 로그"

    @respx.mock
    async def test_request_tool_is_also_guarded(self, monkeypatch, _env):
        """주문 도구의 응답에도 동일한 한도가 적용된다."""
        monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "10")
        respx.post(EXTRACT_URL).mock(
            return_value=httpx.Response(201, json={"command_id": "cmd-1" * 20})
        )

        mcp = create_server()
        with pytest.raises(ResponseTooLargeError):
            await _fn(mcp, "request_extract_log")(**VALID_ARGS)
