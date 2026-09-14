"""MCP 서버 — stdio 전송 방식으로 로그 추출 및 조회 도구를 제공한다."""

from __future__ import annotations

import json
import re

from mcp.server.mcpserver import MCPServer

from extract_error_log_mcp.client import ExtractLogClient
from extract_error_log_mcp.config import (
    CONTENT_ID_KEY,
    DATA_KEY,
    DATE_PATTERN,
    INVALID_DATE_MESSAGE,
    INVALID_TIME_MESSAGE,
    INVALID_TIME_ORDER_MESSAGE,
    INVALID_WAS_INSTANCE_MESSAGE,
    MDCONTENT_NOT_FOUND_MESSAGE_TEMPLATE,
    NO_CONTENT_ID_MESSAGE_TEMPLATE,
    PAYLOAD_DATE_KEY,
    PAYLOAD_HOST_ID_KEY,
    PAYLOAD_TIME_FROM_KEY,
    PAYLOAD_TIME_TO_KEY,
    PAYLOAD_WAS_INSTANCE_ID_KEY,
    REQUEST_FAILED_MESSAGE_TEMPLATE,
    RESULT_FAILED_MESSAGE_TEMPLATE,
    Settings,
    TIME_PATTERN,
    WAS_INSTANCE_TOKEN,
)
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
        if not re.match(DATE_PATTERN, date):
            return INVALID_DATE_MESSAGE

        if not re.match(TIME_PATTERN, time_from) or not re.match(TIME_PATTERN, time_to):
            return INVALID_TIME_MESSAGE

        if time_from >= time_to:
            return INVALID_TIME_ORDER_MESSAGE

        if WAS_INSTANCE_TOKEN not in was_instance_id:
            return INVALID_WAS_INSTANCE_MESSAGE

        payload = {
            PAYLOAD_DATE_KEY: date,
            PAYLOAD_HOST_ID_KEY: host_id,
            PAYLOAD_TIME_FROM_KEY: time_from,
            PAYLOAD_TIME_TO_KEY: time_to,
            PAYLOAD_WAS_INSTANCE_ID_KEY: was_instance_id,
        }

        try:
            result = await client.request_extract_log(payload)
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return REQUEST_FAILED_MESSAGE_TEMPLATE.format(error=exc)

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
            data = list_result.get(DATA_KEY, [])
            if not data:
                return MDCONTENT_NOT_FOUND_MESSAGE_TEMPLATE.format(
                    command_id=command_id
                )

            # 첫 번째 항목의 content_id 가져오기
            first_item = data[0]
            content_id = first_item.get(CONTENT_ID_KEY)

            if not content_id:
                return NO_CONTENT_ID_MESSAGE_TEMPLATE.format(
                    response=json.dumps(first_item, ensure_ascii=False)
                )

            # 2. mdcontent 상세 조회
            detail_result = await client.get_mdcontent(content_id)
            return json.dumps(detail_result, ensure_ascii=False)

        except Exception as exc:
            return RESULT_FAILED_MESSAGE_TEMPLATE.format(error=exc)

    return mcp


def main() -> None:
    """MCP 서버를 stdio 전송 방식으로 실행한다."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
