"""MCP 서버 — stdio 전송 방식으로 원격 서버 파일 읽기 도구를 제공한다."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from read_server_file_mcp.client import ReadServerFileClient
from read_server_file_mcp.config import (
    ADDITIONAL_PARAMS_KEY,
    AGENT_ERROR_SENTINELS,
    AGENT_ID_KEY,
    AGENT_NOT_FOUND_MESSAGE_TEMPLATE,
    COMMAND_ID_KEY,
    COMPLITED_DATE_KEY,
    CREATE_FAILED_MESSAGE_TEMPLATE,
    HOST_ID_KEY,
    MISSING_COMMAND_ID_MESSAGE,
    MISSING_FILE_PATH_MESSAGE,
    MISSING_HOST_ID_MESSAGE,
    MULTIPLE_AGENT_NOTICE_TEMPLATE,
    NO_COMMAND_ID_MESSAGE_TEMPLATE,
    NOT_ABSOLUTE_PATH_MESSAGE_TEMPLATE,
    PATH_TRAVERSAL_MESSAGE_TEMPLATE,
    PATH_TRAVERSAL_TOKEN,
    POSIX_PATH_PREFIX,
    REQUEST_ACCEPTED_NOTICE_TEMPLATE,
    RESULT_DATA_KEY,
    RESULT_FAILED_MESSAGE_TEMPLATE,
    RESULT_MESSAGE_KEY,
    RESULT_NOTICE,
    RESULT_PENDING_MESSAGE_TEMPLATE,
    RESULT_STATUS_KEY,
    RESULT_TEXT_KEY,
    Settings,
    UNC_PATH_PREFIX,
    WINDOWS_PATH_SEPARATORS,
)
from mcp_common.response_limit import limit_response_size

SERVER_NAME = "read-server-file-mcp"
SERVER_INSTRUCTIONS = (
    "서버(호스트)의 특정 위치에 있는 파일 내용을 읽는 MCP 서버입니다. "
    "'OOO 서버의 /var/log/messages 좀 보여줘', '호스트 OOO에 있는 XXX 파일 읽어줘', "
    "'그 서버 설정 파일 내용 확인해줘' 같은 요청이 트리거입니다. "
    "대상 서버는 host_id로 지정하며, 사용자는 이를 '서버', '호스트', '시스템'이라고 "
    "부르기도 합니다 — 모두 같은 값입니다. "
    "host_id와 file_path(절대 경로)는 필수입니다. 둘 중 하나라도 모르면 추측하거나 "
    "비워서 호출하지 말고 사용자에게 되물으세요. "
    "사용 절차는 2단계입니다 — (1) request_read_server_file로 파일 읽기를 주문해 command_id를 "
    "받고, 사용자에게 소요 시간을 안내한 뒤 실제로 대기합니다. "
    "(2) get_read_server_file_result를 command_id로 호출해 결과를 확인합니다. "
    "결과가 아직 없으면 조금 더 기다렸다가 다시 조회하세요. "
    "실제 파일 읽기는 대상 호스트의 에이전트가 수행하므로 즉시 결과가 나오지 않습니다. "
    "조회된 result_text는 파일 내용일 수도 있고 FileNotFound 같은 오류 메시지일 수도 "
    "있습니다. 어느 쪽인지는 AI Agent가 내용을 보고 판단해서 사용자에게 알려야 합니다."
)

REQUEST_TOOL_DESCRIPTION = (
    "서버(호스트)의 특정 위치에 있는 파일을 읽도록 명령을 주문하고 command_id를 반환합니다. "
    "'OOO 서버의 XXX 파일 읽어줘/보여줘/내용 확인해줘' 같은 요청에 이 도구를 사용하세요. "
    "host_id는 사용자가 '서버'/'호스트'/'시스템'이라고 부르는 값이며 필수입니다. "
    "file_path는 읽을 파일의 절대 경로여야 하며 필수입니다 "
    "(예: /var/log/messages, C:\\logs\\app.log). 상대 경로나 '..'는 사용할 수 없습니다. "
    "둘 중 하나라도 모르면 추측하지 말고 사용자에게 되물으세요. "
    "이 도구는 명령을 주문만 합니다 — 파일 내용은 반환하지 않습니다. "
    "호출 후 응답의 notice에 안내된 시간만큼 사용자에게 먼저 알리고 대기한 다음, "
    "get_read_server_file_result를 command_id로 호출해 내용을 확인하세요."
)

RESULT_TOOL_DESCRIPTION = (
    "request_read_server_file로 주문한 파일 읽기 명령의 실행 결과를 command_id로 조회합니다. "
    "응답의 file_path(실제로 읽으라고 지시된 파일 위치)와 result_text(파일 내용)를 확인하세요. "
    "result_text에는 파일 내용이 올 수도 있지만 FileNotFound 등 오류 메시지가 올 수도 "
    "있으므로, 어느 쪽인지는 AI Agent가 내용을 보고 판단해야 합니다. "
    "found가 false이면 에이전트가 아직 결과를 반환하지 않은 것이니, "
    "잠시 더 기다렸다가 같은 command_id로 다시 조회하세요."
)


def create_read_server_file_client() -> ReadServerFileClient:
    """Settings 를 로드하여 ReadServerFileClient 를 생성한다."""
    return ReadServerFileClient(Settings())


# -- 입력 검증 ----------------------------------------------------------------


def _is_absolute_path(file_path: str) -> bool:
    """POSIX(/...) 또는 Windows(C:\\..., C:/..., \\\\srv\\share) 절대 경로인지 판정한다.

    에이전트는 Linux/AIX 와 Windows 양쪽에서 동작하므로 os.path 에 의존하지 않고
    두 형식을 모두 직접 판정한다 (MCP 서버의 OS와 대상 호스트의 OS는 다를 수 있다).
    """
    if file_path.startswith(POSIX_PATH_PREFIX) or file_path.startswith(UNC_PATH_PREFIX):
        return True
    # 드라이브 문자 형식: 'C:\...' 또는 'C:/...'
    return (
        len(file_path) >= 3
        and file_path[0].isalpha()
        and file_path[1] == ":"
        and file_path[2] in WINDOWS_PATH_SEPARATORS
    )


def _validate_file_path(file_path: str) -> None:
    """파일 경로를 사전 검증한다. 위반 시 사유를 담은 ValueError 를 발생시킨다.

    에이전트도 동일한 검사를 하지만, 왕복 대기(수십 초)를 낭비하지 않도록 명백한 오류는
    명령 생성 전에 먼저 거른다.
    """
    if not _is_absolute_path(file_path):
        raise ValueError(
            NOT_ABSOLUTE_PATH_MESSAGE_TEMPLATE.format(file_path=file_path)
        )
    if PATH_TRAVERSAL_TOKEN in file_path:
        raise ValueError(PATH_TRAVERSAL_MESSAGE_TEMPLATE.format(file_path=file_path))


# -- 응답 조립 ----------------------------------------------------------------


def _request_error(message: str) -> str:
    """명령 주문 실패·되묻기 유도 응답을 생성한다."""
    return json.dumps({"requested": False, "message": message}, ensure_ascii=False)


def _result_error(message: str, command_id: str | None = None) -> str:
    """결과 조회 실패·대기 안내 응답을 생성한다."""
    payload: dict[str, Any] = {"found": False}
    if command_id is not None:
        payload["command_id"] = command_id
    payload["message"] = message
    return json.dumps(payload, ensure_ascii=False)


def _match_error_sentinel(result_text: Any) -> str | None:
    """result_text 가 에이전트의 알려진 오류 문구와 '완전히 일치' 하면 그 값을 반환한다.

    파일 내용 자체가 같은 단어를 포함할 수 있으므로 부분 일치로는 판단하지 않는다.
    최종 판단은 호출한 AI Agent 의 몫이며, 이 값은 보조 힌트일 뿐이다.
    """
    if not isinstance(result_text, str):
        return None
    stripped = result_text.strip()
    return stripped if stripped in AGENT_ERROR_SENTINELS else None


def _select_agent(host_id: str, agent_ids: list[str]) -> tuple[str, str | None]:
    """사용할 agent_id 와 (복수일 때의) 안내 문구를 고른다."""
    selected = agent_ids[0]
    if len(agent_ids) == 1:
        return selected, None
    notice = MULTIPLE_AGENT_NOTICE_TEMPLATE.format(
        host_id=host_id,
        count=len(agent_ids),
        selected=selected,
        all_agents=", ".join(agent_ids),
    )
    return selected, notice


def create_server() -> MCPServer:
    """MCPServer 서버를 생성하고 파일 읽기 도구를 등록한다."""
    mcp = MCPServer(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    settings = Settings()
    client = ReadServerFileClient(settings)

    @mcp.tool(description=REQUEST_TOOL_DESCRIPTION)
    @limit_response_size(settings)
    async def request_read_server_file(host_id: str, file_path: str) -> str:
        """서버의 특정 위치 파일을 읽는 명령을 주문하고 command_id 를 반환한다."""
        try:
            host = (host_id or "").strip()
            if not host:
                return _request_error(MISSING_HOST_ID_MESSAGE)

            path = (file_path or "").strip()
            if not path:
                return _request_error(MISSING_FILE_PATH_MESSAGE)

            _validate_file_path(path)

            agent_ids = await client.find_agent_ids(host)
            if not agent_ids:
                return _request_error(
                    AGENT_NOT_FOUND_MESSAGE_TEMPLATE.format(host_id=host)
                )

            agent_id, multiple_notice = _select_agent(host, agent_ids)

            created = await client.create_read_file_command(agent_id, path)
            command_id = created.get(COMMAND_ID_KEY)
            if not command_id:
                return _request_error(
                    NO_COMMAND_ID_MESSAGE_TEMPLATE.format(
                        response=json.dumps(created, ensure_ascii=False)
                    )
                )

            notice = REQUEST_ACCEPTED_NOTICE_TEMPLATE.format(
                wait_seconds=settings.result_wait_seconds
            )
            if multiple_notice:
                notice = f"{multiple_notice} {notice}"

            return json.dumps(
                {
                    "requested": True,
                    "command_id": command_id,
                    "host_id": host,
                    "agent_id": agent_id,
                    "file_path": path,
                    "notice": notice,
                },
                ensure_ascii=False,
            )
        except ValueError as exc:
            # 입력 검증 실패 — API 호출 실패가 아니므로 사유를 그대로 전달한다.
            return _request_error(str(exc))
        except Exception as exc:
            return _request_error(CREATE_FAILED_MESSAGE_TEMPLATE.format(error=exc))

    @mcp.tool(description=RESULT_TOOL_DESCRIPTION)
    @limit_response_size(settings)
    async def get_read_server_file_result(command_id: str) -> str:
        """command_id 로 파일 읽기 결과(파일 위치·파일 내용)를 조회한다."""
        identifier = (command_id or "").strip()
        try:
            if not identifier:
                return _result_error(MISSING_COMMAND_ID_MESSAGE)

            payload = await client.get_command_result(identifier)
            data = payload.get(RESULT_DATA_KEY) if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                return _result_error(
                    RESULT_PENDING_MESSAGE_TEMPLATE.format(
                        command_id=identifier,
                        wait_seconds=settings.result_wait_seconds,
                    ),
                    command_id=identifier,
                )

            result_text = data.get(RESULT_TEXT_KEY)
            return json.dumps(
                {
                    "found": True,
                    "command_id": identifier,
                    "file_path": data.get(ADDITIONAL_PARAMS_KEY),
                    "result_text": result_text,
                    "agent_error_sentinel": _match_error_sentinel(result_text),
                    "host_id": data.get(HOST_ID_KEY),
                    "agent_id": data.get(AGENT_ID_KEY),
                    "result_status": data.get(RESULT_STATUS_KEY),
                    "result_message": data.get(RESULT_MESSAGE_KEY),
                    "complited_date": data.get(COMPLITED_DATE_KEY),
                    "notice": RESULT_NOTICE,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return _result_error(
                RESULT_FAILED_MESSAGE_TEMPLATE.format(error=exc),
                command_id=identifier or None,
            )

    return mcp


def main() -> None:
    """MCP 서버를 stdio 전송 방식으로 실행한다."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
