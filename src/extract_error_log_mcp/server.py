"""MCP 서버 — stdio 전송 방식으로 로그 추출 및 조회 도구를 제공한다."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from extract_error_log_mcp.client import ExtractLogClient
from extract_error_log_mcp.config import Settings
from mcp_common.response_limit import limit_response_size

SERVER_NAME = "extract-error-log-mcp"
SERVER_INSTRUCTIONS = "서버 에러(error) 로그 추출 요청 및 추출된 마크다운 결과를 조회하는 MCP 서버입니다. '서버 ooo에서 error를 찾아줘' 와 같은 요청에 사용하세요."


def create_client() -> ExtractLogClient:
    """Settings 를 로드하여 ExtractLogClient 를 생성한다."""
    return ExtractLogClient(Settings())


def create_server() -> MCPServer:
    """MCPServer 서버를 생성하고 로그 추출 관련 도구를 등록한다."""
    mcp = MCPServer(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    settings = Settings()
    client = ExtractLogClient(settings)

    @mcp.tool()
    @limit_response_size(settings)
    async def request_extract_log(
        date: str,
        host_id: str,
        time_from: str,
        time_to: str,
        was_instance_id: str,
    ) -> str:
        """서버의 '에러(error) 로그' 추출을 요청하고 command_id를 반환합니다.
        '서버 또는 시스템 ooo에서 error를 찾아' 또는 '에러 로그를 확인해줘'와 같은 요청에 이 도구를 사용하세요.
        AI Agent는 이 도구를 호출하여 command_id를 얻은 후, 반드시 사용자에게 "로그 추출에 약 1분 정도 소요됩니다"라고 안내하는 메시지를 먼저 응답해야 합니다. 그 후 실제로 약 1분간 대기(wait)하고 나서 get_extracted_log 도구를 호출해야 합니다.

        Args:
            date: 로그 추출 대상 일자 (포맷: yyyymmdd, 8자리 숫자)
            host_id: 호스트 ID ('서버' 또는 '시스템'이라고도 부름)
            time_from: 검색 시작 시간 (포맷: hhmiss, 6자리 숫자, time_to 보다 이전이어야 함)
            time_to: 검색 종료 시간 (포맷: hhmiss, 6자리 숫자)
            was_instance_id: WAS 인스턴스 ID (반드시 '_MS' 문자열을 포함해야 함, 'OOO 서버의 XXX' 식으로 부를 경우 XXX는 WAS 인스턴스 ID 입니다. 예: 서버 pcbkaa11의 ONL_MS12)
        """
        import re
        if not re.match(r"^\d{8}$", date):
            return "오류: date는 yyyymmdd 형식(8자리 숫자)이어야 합니다."
            
        if not re.match(r"^\d{6}$", time_from) or not re.match(r"^\d{6}$", time_to):
            return "오류: time_from과 time_to는 hhmiss 형식(6자리 숫자)이어야 합니다."

        if time_from >= time_to:
            return "오류: time_from 값은 time_to 보다 작아야 합니다."
            
        if "_MS" not in was_instance_id:
            return "오류: was_instance_id는 반드시 '_MS' 형태를 포함해야 합니다."
            
        payload = {
            "date": date,
            "host_id": host_id,
            "time_from": time_from,
            "time_to": time_to,
            "was_instance_id": was_instance_id,
        }
        
        try:
            result = await client.request_extract_log(payload)
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return f"로그 추출 요청 오류: {exc}"

    @mcp.tool()
    @limit_response_size(settings)
    async def get_extracted_log(command_id: str) -> str:
        """지정된 command_id에 대한 mdcontent(추출된 로그 마크다운 문서)를 조회합니다.
        request_extract_log 호출 후 일정 시간(약 1분) 대기한 뒤에 이 도구를 호출해야 합니다.

        Args:
            command_id: request_extract_log 호출 결과로 받은 command_id
        """
        try:
            # 1. content_id 조회
            list_result = await client.get_mdcontent_list(search_tags=command_id)
            
            # API 응답 구조에 따라 데이터 추출 (일반적으로 'data' 리스트 안에 존재)
            data = list_result.get("data", [])
            if not data:
                return f"command_id '{command_id}'에 해당하는 mdcontent를 찾을 수 없습니다. (아직 생성 중일 수 있습니다.)"
            
            # 첫 번째 항목의 content_id 가져오기
            first_item = data[0]
            content_id = first_item.get("content_id")
            
            if not content_id:
                return f"목록 조회 결과에서 content_id를 찾을 수 없습니다. 응답: {json.dumps(first_item, ensure_ascii=False)}"

            # 2. mdcontent 상세 조회
            detail_result = await client.get_mdcontent(content_id)
            return json.dumps(detail_result, ensure_ascii=False)
            
        except Exception as exc:
            return f"로그 추출 결과 조회 오류: {exc}"

    return mcp


def main() -> None:
    """MCP 서버를 stdio 전송 방식으로 실행한다."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
