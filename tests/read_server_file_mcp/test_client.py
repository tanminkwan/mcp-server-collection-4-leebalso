"""ReadServerFileClient 테스트."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from read_server_file_mcp.client import ReadServerFileClient
from read_server_file_mcp.config import (
    AGENT_LOOKUP_OPERATOR,
    HOST_ID_COLUMN,
    Settings,
)


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("read_server_file_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def settings(monkeypatch) -> Settings:
    monkeypatch.setenv("API_BASE_URL", "https://app.mwm.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    monkeypatch.delenv("API_SSL_VERIFY", raising=False)
    monkeypatch.delenv("API_TIMEOUT", raising=False)
    monkeypatch.delenv("READ_SERVER_FILE_RESULT_WAIT_SECONDS", raising=False)
    return Settings()


@pytest.fixture()
def client(settings) -> ReadServerFileClient:
    return ReadServerFileClient(settings)


AGENT_URL = (
    "https://app.mwm.local:20443/api/v1/model/column_all/ag_agent.agent_id"
)
CREATE_URL = "https://app.mwm.local:20443/api/v1/command_master/create"
RESULT_URL = "https://app.mwm.local:20443/api/v1/command_master/result"


class TestFindAgentIds:
    """host_id 로 agent_id 목록을 조회한다."""

    @respx.mock
    async def test_sends_eql_condition_on_host_id(self, client):
        route = respx.get(AGENT_URL).mock(
            return_value=httpx.Response(200, json={"list": []})
        )

        await client.find_agent_ids("pcbkaa11")

        condition = route.calls.last.request.url.params["condition"]
        assert json.loads(condition) == {
            "column": HOST_ID_COLUMN,
            "operator": AGENT_LOOKUP_OPERATOR,
            "value": "pcbkaa11",
        }

    @respx.mock
    async def test_returns_agent_ids_in_order(self, client):
        respx.get(AGENT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"list": [{"pk": 1, "value": "a_J"}, {"pk": 2, "value": "b_J"}]},
            )
        )

        assert await client.find_agent_ids("h1") == ["a_J", "b_J"]

    @respx.mock
    async def test_returns_empty_list_when_no_agent(self, client):
        respx.get(AGENT_URL).mock(
            return_value=httpx.Response(200, json={"list": []})
        )

        assert await client.find_agent_ids("nope") == []

    @respx.mock
    async def test_ignores_entries_without_value(self, client):
        """value 가 없거나 비어 있는 항목은 제외한다."""
        respx.get(AGENT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"list": [{"pk": 1}, {"pk": 2, "value": ""}, {"pk": 3, "value": "ok_J"}]},
            )
        )

        assert await client.find_agent_ids("h1") == ["ok_J"]

    @respx.mock
    async def test_tolerates_missing_list_key(self, client):
        respx.get(AGENT_URL).mock(return_value=httpx.Response(200, json={}))

        assert await client.find_agent_ids("h1") == []

    @respx.mock
    async def test_tolerates_non_object_payload(self, client):
        """응답이 객체가 아니어도 0건으로 처리한다."""
        respx.get(AGENT_URL).mock(return_value=httpx.Response(200, json=[]))

        assert await client.find_agent_ids("h1") == []

    @respx.mock
    async def test_tolerates_non_list_under_list_key(self, client):
        respx.get(AGENT_URL).mock(
            return_value=httpx.Response(200, json={"list": None})
        )

        assert await client.find_agent_ids("h1") == []

    @respx.mock
    async def test_sends_authorization_header(self, client):
        route = respx.get(AGENT_URL).mock(
            return_value=httpx.Response(200, json={"list": []})
        )

        await client.find_agent_ids("h1")

        assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"

    @respx.mock
    async def test_raises_on_http_error(self, client):
        respx.get(AGENT_URL).mock(return_value=httpx.Response(500))

        with pytest.raises(httpx.HTTPStatusError):
            await client.find_agent_ids("h1")


class TestCreateReadFileCommand:
    """파일 읽기 명령 생성."""

    @respx.mock
    async def test_posts_expected_payload(self, client):
        route = respx.post(CREATE_URL).mock(
            return_value=httpx.Response(201, json={"command_id": "abc"})
        )

        await client.create_read_file_command("agent_J", "/var/log/messages")

        payload = json.loads(route.calls.last.request.content)
        assert payload == {
            "command_type_id": "COMMON.READFILE",
            "target_agent_id": ["agent_J"],
            "parameters": "/var/log/messages",
        }

    @respx.mock
    async def test_parameters_is_plain_string_not_object(self, client):
        """에이전트는 additional_params 를 경로 문자열로 읽으므로 객체로 보내면 안 된다."""
        route = respx.post(CREATE_URL).mock(
            return_value=httpx.Response(201, json={"command_id": "abc"})
        )

        await client.create_read_file_command("agent_J", "/tmp/a.log")

        payload = json.loads(route.calls.last.request.content)
        assert isinstance(payload["parameters"], str)

    @respx.mock
    async def test_returns_response_json(self, client):
        respx.post(CREATE_URL).mock(
            return_value=httpx.Response(
                201, json={"command_id": "abc", "message": "OK", "return_code": 1}
            )
        )

        result = await client.create_read_file_command("agent_J", "/tmp/a.log")

        assert result["command_id"] == "abc"

    @respx.mock
    async def test_sends_authorization_header(self, client):
        route = respx.post(CREATE_URL).mock(
            return_value=httpx.Response(201, json={"command_id": "abc"})
        )

        await client.create_read_file_command("agent_J", "/tmp/a.log")

        assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"

    @respx.mock
    async def test_raises_on_http_error(self, client):
        respx.post(CREATE_URL).mock(return_value=httpx.Response(400))

        with pytest.raises(httpx.HTTPStatusError):
            await client.create_read_file_command("agent_J", "/tmp/a.log")


class TestGetCommandResult:
    """명령 실행 결과 조회."""

    @respx.mock
    async def test_queries_by_command_id(self, client):
        route = respx.get(RESULT_URL).mock(
            return_value=httpx.Response(200, json={"data": None})
        )

        await client.get_command_result("cmd-1")

        assert dict(route.calls.last.request.url.params) == {"command_id": "cmd-1"}

    @respx.mock
    async def test_returns_response_json(self, client):
        respx.get(RESULT_URL).mock(
            return_value=httpx.Response(
                200, json={"data": {"result_text": "hello"}, "return_code": 1}
            )
        )

        result = await client.get_command_result("cmd-1")

        assert result["data"]["result_text"] == "hello"

    @respx.mock
    async def test_raises_on_http_error(self, client):
        respx.get(RESULT_URL).mock(return_value=httpx.Response(500))

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_command_result("cmd-1")
