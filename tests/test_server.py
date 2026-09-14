"""MCP 서버 테스트."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from email_mcp.server import create_server, create_email_client
from mcp_common.config import MAX_RESPONSE_BYTES_ENV
from mcp_common.response_limit import ResponseTooLargeError


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("email_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def _env(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://api.test.local:20443")
    monkeypatch.setenv("API_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("API_SSL_VERIFY", "false")
    monkeypatch.delenv(MAX_RESPONSE_BYTES_ENV, raising=False)


@pytest.fixture()
def mcp(_env):
    return create_server()


@pytest.fixture()
def client(_env):
    return create_email_client()


class TestCreateServer:
    """서버 생성 테스트."""

    def test_server_name(self, mcp):
        """서버 이름이 올바르게 설정된다."""
        assert mcp.name == "email-mcp"

    def test_server_has_tools(self, mcp):
        """이메일 발송 도구가 등록되어 있다."""
        # FastMCP 내부 도구 목록 확인
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "send_html_email" in tool_names
        assert "send_markdown_email" in tool_names


class TestSendHtmlEmailTool:
    """send_html_email 도구 테스트."""

    @respx.mock
    async def test_send_html_email_returns_success(self, mcp, _env):
        """HTML 이메일 발송 도구가 성공 메시지를 반환한다."""
        respx.post("https://api.test.local:20443/api/v1/email/send").mock(
            return_value=httpx.Response(200, json={"message": "Email sent successfully"})
        )

        tool_fn = mcp._tool_manager._tools["send_html_email"].fn
        result = await tool_fn(
            receivers="user@example.com",
            subject="제목",
            content="<p>본문</p>",
            sender_name="발신자",
        )

        assert "Email sent successfully" in result

    @respx.mock
    async def test_send_html_email_without_sender_name(self, mcp, _env):
        """sender_name 없이 HTML 이메일 발송이 가능하다."""
        respx.post("https://api.test.local:20443/api/v1/email/send").mock(
            return_value=httpx.Response(200, json={"message": "Email sent successfully"})
        )

        tool_fn = mcp._tool_manager._tools["send_html_email"].fn
        result = await tool_fn(
            receivers="user@example.com",
            subject="제목",
            content="<p>본문</p>",
        )

        assert "Email sent successfully" in result

    @respx.mock
    async def test_send_html_email_api_error(self, mcp, _env):
        """API 에러 시 에러 메시지를 반환한다."""
        respx.post("https://api.test.local:20443/api/v1/email/send").mock(
            return_value=httpx.Response(500, json={"message": "메일 발송 오류"})
        )

        tool_fn = mcp._tool_manager._tools["send_html_email"].fn
        result = await tool_fn(
            receivers="user@example.com",
            subject="제목",
            content="<p>본문</p>",
        )

        assert "오류" in result or "error" in result.lower() or "500" in result


class TestSendMarkdownEmailTool:
    """send_markdown_email 도구 테스트."""

    @respx.mock
    async def test_send_markdown_email_returns_success(self, mcp, _env):
        """Markdown 이메일 발송 도구가 성공 메시지를 반환한다."""
        respx.post("https://api.test.local:20443/api/v1/email/send_markdown").mock(
            return_value=httpx.Response(200, json={"message": "Email sent successfully"})
        )

        tool_fn = mcp._tool_manager._tools["send_markdown_email"].fn
        result = await tool_fn(
            receivers="user@example.com",
            subject="제목",
            content="# 제목\n본문",
            sender_name="발신자",
        )

        assert "Email sent successfully" in result

    @respx.mock
    async def test_send_markdown_email_api_error(self, mcp, _env):
        """Markdown 발송 API 에러 시 에러 메시지를 반환한다."""
        respx.post("https://api.test.local:20443/api/v1/email/send_markdown").mock(
            return_value=httpx.Response(400, json={"message": "필수 파라미터 누락"})
        )

        tool_fn = mcp._tool_manager._tools["send_markdown_email"].fn
        result = await tool_fn(
            receivers="",
            subject="",
            content="",
        )

        assert "오류" in result or "error" in result.lower() or "400" in result

    @respx.mock
    async def test_send_email_receiver_mapping(self, monkeypatch):
        """수신자 이름 매핑 및 오류 처리 테스트."""
        monkeypatch.setenv("API_BASE_URL", "https://api.test.local:20443")
        monkeypatch.setenv("API_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("EMAIL_RECIPIENT_MAPPING", "홍길동:hong@example.com")

        route = respx.post("https://api.test.local:20443/api/v1/email/send").mock(
            return_value=httpx.Response(200, json={"message": "Email sent successfully"})
        )

        mcp_server = create_server()
        tool_fn = mcp_server._tool_manager._tools["send_html_email"].fn

        # 1. 매핑된 이름과 이메일 주소 혼합 테스트
        result = await tool_fn(
            receivers="홍길동, direct@example.com",
            subject="제목",
            content="<p>본문</p>",
        )
        assert "Email sent successfully" in result
        assert route.calls.last.request.content != b""
        
        # 2. 매핑 정보 없는 이름 테스트 -> 오류 반환
        error_result = await tool_fn(
            receivers="없는사람",
            subject="제목",
            content="<p>본문</p>",
        )
        assert "이메일 발송 오류" in error_result
        assert "없는사람" in error_result



class TestResponseSizeLimit:
    """응답 크기 제한 테스트."""

    @respx.mock
    async def test_oversized_response_raises_error(self, monkeypatch, _env):
        """한도를 넘는 응답은 잘리지 않고 '너무 크다'는 오류로 반환된다."""
        monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "50")
        respx.post("https://api.test.local:20443/api/v1/email/send").mock(
            return_value=httpx.Response(200, json={"message": "x" * 500})
        )

        tool_fn = create_server()._tool_manager._tools["send_html_email"].fn
        with pytest.raises(ResponseTooLargeError) as exc_info:
            await tool_fn(
                receivers="user@example.com", subject="제목", content="<p>본문</p>"
            )
        assert "너무 커서" in str(exc_info.value)

    @respx.mock
    async def test_response_within_limit_passes_through(self, _env):
        """기본 한도(30KB) 이내 응답은 그대로 반환된다."""
        respx.post("https://api.test.local:20443/api/v1/email/send").mock(
            return_value=httpx.Response(200, json={"message": "Email sent successfully"})
        )

        tool_fn = create_server()._tool_manager._tools["send_html_email"].fn
        result = await tool_fn(
            receivers="user@example.com", subject="제목", content="<p>본문</p>"
        )

        assert "Email sent successfully" in result
