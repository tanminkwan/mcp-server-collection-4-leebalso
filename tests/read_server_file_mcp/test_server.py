"""read_server_file_mcp MCP 서버 테스트."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from read_server_file_mcp.config import (
    AGENT_NOT_FOUND_MESSAGE_TEMPLATE,
    MISSING_COMMAND_ID_MESSAGE,
    MISSING_FILE_PATH_MESSAGE,
    MISSING_HOST_ID_MESSAGE,
    NOT_ABSOLUTE_PATH_MESSAGE_TEMPLATE,
    NO_COMMAND_ID_MESSAGE_TEMPLATE,
    PATH_TRAVERSAL_MESSAGE_TEMPLATE,
    RESULT_PENDING_MESSAGE_TEMPLATE,
)
from read_server_file_mcp.server import create_read_server_file_client, create_server


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("read_server_file_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def _env(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    monkeypatch.delenv("API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("READ_SERVER_FILE_RESULT_WAIT_SECONDS", raising=False)


@pytest.fixture()
def mcp(_env):
    return create_server()


AGENT_URL = (
    "https://app.mwm.local:20443/api/v1/model/column_all/ag_agent.agent_id"
)
CREATE_URL = "https://app.mwm.local:20443/api/v1/command_master/create"
RESULT_URL = "https://app.mwm.local:20443/api/v1/command_master/result"


def _tool(mcp, name):
    return mcp._tool_manager._tools[name]


def _fn(mcp, name):
    return _tool(mcp, name).fn


def _agents(*agent_ids):
    return {"list": [{"pk": i, "value": a} for i, a in enumerate(agent_ids, start=1)]}


def _mock_agent_lookup(*agent_ids):
    return respx.get(AGENT_URL).mock(
        return_value=httpx.Response(200, json=_agents(*agent_ids))
    )


def _mock_create(command_id="cmd-1"):
    return respx.post(CREATE_URL).mock(
        return_value=httpx.Response(
            201, json={"command_id": command_id, "message": "OK", "return_code": 1}
        )
    )


def _result_payload(**overrides):
    data = {
        "command_id": "cmd-1",
        "agent_id": "pcbkaa11_user_J",
        "host_id": "pcbkaa11",
        "command_type_id": "COMMON.READFILE",
        "command_class": "ReadFullPathFile",
        "additional_params": "/var/log/messages",
        "result_text": "line1\nline2",
        "result_status": "COMPLITED",
        "result_message": "",
        "complited_date": "2026-09-14 14:52:03",
        "create_on": "2026-09-14 14:51:58",
    }
    data.update(overrides)
    return {"data": data, "message": "OK", "return_code": 1}


class TestToolRegistration:
    """도구 등록 및 스키마."""

    def test_both_tools_registered(self, mcp):
        assert "request_read_server_file" in mcp._tool_manager._tools
        assert "get_read_server_file_result" in mcp._tool_manager._tools

    def test_request_tool_requires_host_id_and_file_path(self, mcp):
        schema = _tool(mcp, "request_read_server_file").parameters

        assert set(schema["required"]) == {"host_id", "file_path"}

    def test_result_tool_requires_command_id(self, mcp):
        schema = _tool(mcp, "get_read_server_file_result").parameters

        assert schema["required"] == ["command_id"]

    def test_create_read_server_file_client_builds_client(self, _env):
        from read_server_file_mcp.client import ReadServerFileClient

        assert isinstance(create_read_server_file_client(), ReadServerFileClient)


class TestRequestReadFileValidation:
    """request_read_server_file 입력 검증 — API를 호출하지 않고 되묻기를 유도한다."""

    @respx.mock
    @pytest.mark.parametrize("host_id", ["", "   "])
    async def test_missing_host_id_asks_back(self, mcp, host_id):
        route = _mock_agent_lookup("a_J")

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id=host_id, file_path="/tmp/a")
        )

        assert result["requested"] is False
        assert result["message"] == MISSING_HOST_ID_MESSAGE
        assert not route.called

    @respx.mock
    @pytest.mark.parametrize("file_path", ["", "   "])
    async def test_missing_file_path_asks_back(self, mcp, file_path):
        route = _mock_agent_lookup("a_J")

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path=file_path)
        )

        assert result["requested"] is False
        assert result["message"] == MISSING_FILE_PATH_MESSAGE
        assert not route.called

    @respx.mock
    @pytest.mark.parametrize("file_path", ["var/log/messages", "./a.log", "a.log"])
    async def test_relative_path_rejected(self, mcp, file_path):
        route = _mock_agent_lookup("a_J")

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path=file_path)
        )

        assert result["requested"] is False
        assert result["message"] == NOT_ABSOLUTE_PATH_MESSAGE_TEMPLATE.format(
            file_path=file_path
        )
        assert not route.called

    @respx.mock
    async def test_path_traversal_rejected(self, mcp):
        route = _mock_agent_lookup("a_J")

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(
                host_id="h1", file_path="/var/log/../../etc/passwd"
            )
        )

        assert result["requested"] is False
        assert "PATH" in result["message"].upper() or ".." in result["message"]
        assert result["message"] == PATH_TRAVERSAL_MESSAGE_TEMPLATE.format(
            file_path="/var/log/../../etc/passwd"
        )
        assert not route.called

    @respx.mock
    @pytest.mark.parametrize(
        "file_path",
        ["/var/log/messages", "C:\\logs\\app.log", "C:/logs/app.log", "\\\\srv\\share\\a.log"],
    )
    async def test_absolute_paths_accepted(self, mcp, file_path):
        """POSIX 및 Windows 절대 경로를 모두 허용한다."""
        _mock_agent_lookup("a_J")
        _mock_create()

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path=file_path)
        )

        assert result["requested"] is True
        assert result["file_path"] == file_path

    @respx.mock
    async def test_trims_whitespace_around_inputs(self, mcp):
        lookup = _mock_agent_lookup("a_J")
        create = _mock_create()

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(
                host_id="  h1  ", file_path="  /tmp/a.log  "
            )
        )

        assert json.loads(lookup.calls.last.request.url.params["condition"])["value"] == "h1"
        assert json.loads(create.calls.last.request.content)["parameters"] == "/tmp/a.log"
        assert result["file_path"] == "/tmp/a.log"


class TestRequestReadFileFlow:
    """request_read_server_file 정상 흐름."""

    @respx.mock
    async def test_resolves_agent_and_creates_command(self, mcp):
        lookup = _mock_agent_lookup("pcbkaa11_user_J")
        create = _mock_create("61022517ccc1")

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(
                host_id="pcbkaa11", file_path="/var/log/messages"
            )
        )

        assert json.loads(lookup.calls.last.request.url.params["condition"])["value"] == (
            "pcbkaa11"
        )
        assert json.loads(create.calls.last.request.content) == {
            "command_type_id": "COMMON.READFILE",
            "target_agent_id": ["pcbkaa11_user_J"],
            "parameters": "/var/log/messages",
        }
        assert result == {
            "requested": True,
            "command_id": "61022517ccc1",
            "host_id": "pcbkaa11",
            "agent_id": "pcbkaa11_user_J",
            "file_path": "/var/log/messages",
            "notice": result["notice"],
        }

    @respx.mock
    async def test_notice_mentions_wait_and_next_tool(self, mcp):
        _mock_agent_lookup("a_J")
        _mock_create()

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path="/tmp/a.log")
        )

        assert "30" in result["notice"]
        assert "get_read_server_file_result" in result["notice"]

    @respx.mock
    async def test_wait_seconds_from_env_appears_in_notice(self, monkeypatch, _env):
        monkeypatch.setenv("READ_SERVER_FILE_RESULT_WAIT_SECONDS", "45")
        server = create_server()
        _mock_agent_lookup("a_J")
        _mock_create()

        result = json.loads(
            await _fn(server, "request_read_server_file")(host_id="h1", file_path="/tmp/a.log")
        )

        assert "45" in result["notice"]

    @respx.mock
    async def test_agent_not_found(self, mcp):
        _mock_agent_lookup()
        create = _mock_create()

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="ghost", file_path="/tmp/a.log")
        )

        assert result["requested"] is False
        assert result["message"] == AGENT_NOT_FOUND_MESSAGE_TEMPLATE.format(
            host_id="ghost"
        )
        assert not create.called

    @respx.mock
    async def test_multiple_agents_uses_first_and_notices_all(self, mcp):
        _mock_agent_lookup("first_J", "second_J")
        create = _mock_create()

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path="/tmp/a.log")
        )

        assert result["agent_id"] == "first_J"
        assert json.loads(create.calls.last.request.content)["target_agent_id"] == [
            "first_J"
        ]
        assert "second_J" in result["notice"]

    @respx.mock
    async def test_missing_command_id_in_response(self, mcp):
        _mock_agent_lookup("a_J")
        respx.post(CREATE_URL).mock(
            return_value=httpx.Response(201, json={"message": "OK", "return_code": 1})
        )

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path="/tmp/a.log")
        )

        assert result["requested"] is False
        assert result["message"] == NO_COMMAND_ID_MESSAGE_TEMPLATE.format(
            response=json.dumps({"message": "OK", "return_code": 1}, ensure_ascii=False)
        )

    @respx.mock
    async def test_agent_lookup_http_error(self, mcp):
        respx.get(AGENT_URL).mock(return_value=httpx.Response(500))

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path="/tmp/a.log")
        )

        assert result["requested"] is False
        assert "오류" in result["message"]

    @respx.mock
    async def test_create_http_error(self, mcp):
        _mock_agent_lookup("a_J")
        respx.post(CREATE_URL).mock(return_value=httpx.Response(400))

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path="/tmp/a.log")
        )

        assert result["requested"] is False
        assert "오류" in result["message"]

    @respx.mock
    async def test_unexpected_exception_is_wrapped(self, mcp):
        respx.get(AGENT_URL).mock(side_effect=httpx.ConnectError("boom"))

        result = json.loads(
            await _fn(mcp, "request_read_server_file")(host_id="h1", file_path="/tmp/a.log")
        )

        assert result["requested"] is False
        assert "오류" in result["message"]


class TestGetReadFileResult:
    """get_read_server_file_result 조회."""

    @respx.mock
    async def test_missing_command_id_asks_back(self, mcp):
        route = respx.get(RESULT_URL).mock(
            return_value=httpx.Response(200, json=_result_payload())
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="  "))

        assert result["found"] is False
        assert result["message"] == MISSING_COMMAND_ID_MESSAGE
        assert not route.called

    @respx.mock
    async def test_returns_file_path_and_content(self, mcp):
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(200, json=_result_payload())
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["found"] is True
        assert result["file_path"] == "/var/log/messages"
        assert result["result_text"] == "line1\nline2"
        assert result["host_id"] == "pcbkaa11"
        assert result["agent_id"] == "pcbkaa11_user_J"
        assert result["result_status"] == "COMPLITED"
        assert result["complited_date"] == "2026-09-14 14:52:03"

    @respx.mock
    async def test_queries_by_command_id(self, mcp):
        route = respx.get(RESULT_URL).mock(
            return_value=httpx.Response(200, json=_result_payload())
        )

        await _fn(mcp, "get_read_server_file_result")(command_id="  cmd-1  ")

        assert dict(route.calls.last.request.url.params) == {"command_id": "cmd-1"}

    @respx.mock
    async def test_pending_when_data_is_null(self, mcp):
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(
                200, json={"data": None, "message": "No result found", "return_code": 0}
            )
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["found"] is False
        assert result["command_id"] == "cmd-1"
        assert result["message"] == RESULT_PENDING_MESSAGE_TEMPLATE.format(
            command_id="cmd-1", wait_seconds=30
        )

    @respx.mock
    async def test_pending_when_data_key_absent(self, mcp):
        respx.get(RESULT_URL).mock(return_value=httpx.Response(200, json={}))

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["found"] is False

    @respx.mock
    async def test_notice_tells_agent_to_judge_content_or_error(self, mcp):
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(200, json=_result_payload())
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert "result_text" in result["notice"]
        assert "판단" in result["notice"]

    @respx.mock
    async def test_http_error_is_reported(self, mcp):
        respx.get(RESULT_URL).mock(return_value=httpx.Response(500))

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["found"] is False
        assert "오류" in result["message"]


class TestErrorSentinelHint:
    """result_text 가 에이전트의 알려진 오류 문구와 정확히 일치하는지 표시한다."""

    @respx.mock
    @pytest.mark.parametrize(
        "sentinel",
        [
            "Error:FileNotFoundException",
            "Error:IOException",
            "Error:UnsupportedEncodingException",
            "Error:NoSuchAlgorithmException",
            "NO CHANGE",
        ],
    )
    async def test_known_sentinels_flagged(self, mcp, sentinel):
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(200, json=_result_payload(result_text=sentinel))
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["found"] is True
        assert result["agent_error_sentinel"] == sentinel
        assert result["result_text"] == sentinel

    @respx.mock
    async def test_normal_content_not_flagged(self, mcp):
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(200, json=_result_payload())
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["agent_error_sentinel"] is None

    @respx.mock
    async def test_content_merely_containing_error_word_not_flagged(self, mcp):
        """파일 내용에 오류 문구가 포함돼 있을 뿐이면 단정하지 않는다."""
        text = "2026-09-14 ERROR FileNotFoundException at Foo.java:12"
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(200, json=_result_payload(result_text=text))
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["agent_error_sentinel"] is None
        assert result["result_text"] == text

    @respx.mock
    async def test_sentinel_match_ignores_surrounding_whitespace(self, mcp):
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(
                200, json=_result_payload(result_text="  Error:FileNotFoundException\n")
            )
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["agent_error_sentinel"] == "Error:FileNotFoundException"

    @respx.mock
    async def test_non_string_result_text_is_passed_through(self, mcp):
        """result_text 가 JSON 으로 파싱돼 올 수도 있다 (스펙상 object/array 허용)."""
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(
                200, json=_result_payload(result_text={"a": 1})
            )
        )

        result = json.loads(await _fn(mcp, "get_read_server_file_result")(command_id="cmd-1"))

        assert result["result_text"] == {"a": 1}
        assert result["agent_error_sentinel"] is None


class TestServerMetadata:
    """AI Agent 사용성을 위한 메타데이터."""

    def test_instructions_mention_host_aliases(self, mcp):
        instructions = mcp.instructions

        assert "host_id" in instructions
        for alias in ("서버", "호스트"):
            assert alias in instructions

    def test_instructions_mention_two_step_flow(self, mcp):
        instructions = mcp.instructions

        assert "request_read_server_file" in instructions
        assert "get_read_server_file_result" in instructions

    def test_instructions_mention_error_judgement(self, mcp):
        assert "판단" in mcp.instructions

    def test_request_tool_description_mentions_absolute_path(self, mcp):
        assert "절대" in _tool(mcp, "request_read_server_file").description

    def test_result_tool_description_mentions_error_possibility(self, mcp):
        description = _tool(mcp, "get_read_server_file_result").description

        assert "오류" in description or "error" in description.lower()


class TestMain:
    """엔트리포인트."""

    def test_main_runs_stdio(self, _env):
        from read_server_file_mcp import server as server_module

        with patch.object(server_module, "create_server") as create:
            server_module.main()

        create.return_value.run.assert_called_once_with(transport="stdio")
