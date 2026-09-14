"""MCP 서버 — stdio 전송 방식으로 이메일 발송 도구를 제공한다."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from email_mcp.client import EmailClient
from email_mcp.config import Settings
from mcp_common.response_limit import limit_response_size

SERVER_NAME = "email-mcp"
SERVER_INSTRUCTIONS = "EmailApi를 통해 HTML 및 Markdown 이메일을 발송하는 MCP 서버입니다. 수신자 지정 시 이메일 주소뿐만 아니라 사전에 등록된 이름(예: '홍길동')을 사용할 수 있습니다."


def create_email_client() -> EmailClient:
    """Settings 를 로드하여 EmailClient 를 생성한다."""
    return EmailClient(Settings())


def create_server() -> MCPServer:
    """MCPServer 서버를 생성하고 이메일 도구를 등록한다."""
    mcp = MCPServer(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    settings = Settings()
    email_client = EmailClient(settings)

    def _resolve_receivers(receivers_str: str) -> str:
        resolved = []
        for r in receivers_str.split(","):
            r = r.strip()
            if not r:
                continue
            if "@" in r:
                resolved.append(r)
            else:
                mapped_email = settings.recipient_mapping.get(r)
                if not mapped_email:
                    raise ValueError(f"수신자 '{r}'에 대한 이메일 주소를 찾을 수 없습니다. (매핑 정보 없음)")
                resolved.append(mapped_email)
        return ",".join(resolved)

    @mcp.tool()
    @limit_response_size(settings)
    async def send_html_email(
        receivers: str,
        subject: str,
        content: str,
        sender_name: str | None = None,
    ) -> str:
        """HTML 이메일을 발송합니다. content에 HTML 태그가 포함된 경우 이 도구를 사용하세요. 일반 텍스트(plain text)도 이 도구로 발송할 수 있습니다.

        Args:
            receivers: 수신자 이름 또는 이메일 주소 (여러 명일 경우 콤마로 구분). 등록된 이름인 경우 서버가 자동으로 이메일 주소로 변환합니다.
            subject: 메일 제목
            content: 메일 본문 (HTML 태그 또는 일반 텍스트)
            sender_name: 발신인 표시 이름 (선택)
        """
        try:
            resolved_receivers = _resolve_receivers(receivers)
            result = await email_client.send_html(
                receivers=resolved_receivers,
                subject=subject,
                content=content,
                sender_name=sender_name,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return f"이메일 발송 오류: {exc}"

    @mcp.tool()
    @limit_response_size(settings)
    async def send_markdown_email(
        receivers: str,
        subject: str,
        content: str,
        sender_name: str | None = None,
    ) -> str:
        """Markdown 이메일을 발송합니다. content에 Markdown 문법(#, **, ```, 표, Mermaid 등)이 포함된 경우 이 도구를 사용하세요. 서버가 Markdown을 HTML로 자동 변환하여 발송합니다.

        Args:
            receivers: 수신자 이름 또는 이메일 주소 (여러 명일 경우 콤마로 구분). 등록된 이름인 경우 서버가 자동으로 이메일 주소로 변환합니다.
            subject: 메일 제목
            content: 메일 본문 (Markdown 형식 — 헤더, 목록, 표, 코드블록, Mermaid 다이어그램 지원)
            sender_name: 발신인 표시 이름 (선택)
        """
        try:
            resolved_receivers = _resolve_receivers(receivers)
            result = await email_client.send_markdown(
                receivers=resolved_receivers,
                subject=subject,
                content=content,
                sender_name=sender_name,
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return f"이메일 발송 오류: {exc}"

    return mcp


def main() -> None:
    """MCP 서버를 stdio 전송 방식으로 실행한다."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
