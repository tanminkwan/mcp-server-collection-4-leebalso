"""MCP 서버 — stdio 전송 방식으로 WAS/WEB 설정 변경 이력 조회 도구를 제공한다."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

from config_diff_mcp.client import DiffClient
from config_diff_mcp.config import (
    CREATE_ON_FORMATS,
    DATE_FORMAT,
    DETAIL_NOT_FOUND_MESSAGE_TEMPLATE,
    EXCLUDED_DETAIL_FIELDS,
    INVALID_DATE_MESSAGE_TEMPLATE,
    LIST_RESPONSE_DATA_KEY,
    MULTIPLE_RESULT_NOTICE_TEMPLATE,
    NOT_FOUND_MESSAGE,
    REQUEST_FAILED_MESSAGE_TEMPLATE,
    ResourceSpec,
    Settings,
    WAS_CONFIG_FILE_NAME,
    WAS_RESOURCE,
    WEB_CONFIG_FILE_NAME,
    WEB_RESOURCE,
)

SERVER_NAME = "config-diff-mcp"
SERVER_INSTRUCTIONS = (
    "WAS/WEB 미들웨어 설정 파일의 변경 이력을 조회하는 MCP 서버입니다. "
    f"WAS 도메인 설정({WAS_CONFIG_FILE_NAME}) 변경은 get_diff_was를, "
    f"WEB 서버 설정({WEB_CONFIG_FILE_NAME}) 변경은 get_diff_web을 사용하세요. "
    "사용자는 WAS/WEB이라는 말 대신 설정 파일명으로 지칭하기도 합니다 — "
    f"'{WAS_CONFIG_FILE_NAME}'이라고 하면 get_diff_was, "
    f"'{WEB_CONFIG_FILE_NAME}'이라고 하면 get_diff_web입니다. "
    "'최근 OOO 서버 web 설정 바뀐 거 있어?', '8월 11일 WAS 도메인 설정 변경 내역 알려줘', "
    f"'OOO 서버 {WEB_CONFIG_FILE_NAME} 언제 바뀌었어?' 같은 요청이 트리거입니다. "
    "조회 대상은 반드시 지정해야 합니다 — get_diff_web은 host_id(서버/시스템), "
    "get_diff_was는 domain_id(WAS 도메인)가 필수입니다. 사용자가 대상을 말하지 않았다면 "
    "추측하거나 비워서 호출하지 말고 사용자에게 되물으세요. 특히 WAS는 서버명으로 조회할 수 없어, "
    "서버명만 알고 있다면 WAS 도메인 ID를 사용자에게 확인해야 합니다. "
    "날짜를 언급하지 않으면 start_date/end_date를 비워 호출하세요 — 가장 최근 1건이 반환됩니다. "
    "날짜는 반드시 YYYY-MM-DD 형식으로 변환해 전달해야 하며, 사용자가 연도를 말하지 않았다면 "
    "현재 시각을 기준으로 판단해 채워야 합니다."
)

# 도구 설명 — 설정 파일명을 config 상수에서 주입해, 사용자가 파일명으로 지칭해도
# AI Agent가 올바른 도구를 선택할 수 있도록 한다.
_COMMON_TOOL_DESCRIPTION = (
    "날짜를 지정하지 않으면 가장 최근 변경 1건을 반환합니다('최근 변경 내역' 요청). "
    "하루만 지목하면(start_date만, 또는 start_date == end_date) 서버가 앞뒤로 하루씩 여유를 두어 "
    "조회합니다. 날짜는 YYYY-MM-DD 형식이어야 하며, 연도를 사용자가 말하지 않았다면 호출자가 "
    "현재 시각 기준으로 판단해 채워 주세요. "
    "변경 내역이 2건 이상이면 가장 최근 1건만 반환하고 notice에 전체 건수를 안내합니다. "
    "응답에는 이전 설정 전문(old)이 포함되지 않습니다 — 필요하면 new와 unified_diff로 복원하세요."
)

WEB_TOOL_DESCRIPTION = (
    f"WEB 서버 설정 파일({WEB_CONFIG_FILE_NAME})의 변경 내역을 조회합니다. "
    f"사용자가 'web', '웹', '웹서버' 대신 '{WEB_CONFIG_FILE_NAME}'이라고 지칭해도 이 도구를 "
    "사용하세요. host_id는 필수입니다 — 사용자가 '서버' 또는 '시스템'이라고 부르는 값이며, "
    "모르면 추측하지 말고 사용자에게 되물으세요. " + _COMMON_TOOL_DESCRIPTION
)

WAS_TOOL_DESCRIPTION = (
    f"WAS 도메인 설정 파일({WAS_CONFIG_FILE_NAME})의 변경 내역을 조회합니다. "
    f"사용자가 'was', '웨스', '도메인' 대신 '{WAS_CONFIG_FILE_NAME}'이라고 지칭해도 이 도구를 "
    "사용하세요. domain_id는 필수이며, WAS는 서버명(host_id)으로는 조회할 수 없습니다 — "
    "사용자가 서버명만 알려 준 경우 그 값을 domain_id에 넣지 말고 WAS 도메인 ID를 되물으세요. "
    + _COMMON_TOOL_DESCRIPTION
)


def create_diff_client() -> DiffClient:
    """Settings 를 로드하여 DiffClient 를 생성한다."""
    return DiffClient(Settings())


def _parse_date(value: str) -> datetime:
    """YYYY-MM-DD 문자열을 날짜로 파싱한다. 형식이 다르면 ValueError 를 발생시킨다."""
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError as exc:
        raise ValueError(
            INVALID_DATE_MESSAGE_TEMPLATE.format(date_format="YYYY-MM-DD", value=value)
        ) from exc


def _normalize_date_range(
    start_date: str, end_date: str, padding_days: int
) -> dict[str, str]:
    """입력 날짜를 목록 조회용 쿼리 파라미터로 정규화한다.

    둘 다 비어 있으면 날짜 조건을 보내지 않는다(API가 최근 1건만 반환한다).
    한쪽만 있거나 두 값이 같으면 단일 일자로 보고 앞뒤로 padding_days 만큼 확장한다.
    서로 다른 두 값이 주어지면 사용자가 의도한 구간이므로 그대로 사용한다.
    """
    start = (start_date or "").strip()
    end = (end_date or "").strip()

    if not start and not end:
        return {}

    anchor = start or end
    if not start or not end or start == end:
        pivot = _parse_date(anchor)
        delta = timedelta(days=padding_days)
        return {
            "start_date": (pivot - delta).strftime(DATE_FORMAT),
            "end_date": (pivot + delta).strftime(DATE_FORMAT),
        }

    _parse_date(start)
    _parse_date(end)
    return {"start_date": start, "end_date": end}


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    """목록 응답에서 레코드 배열을 꺼낸다.

    실제 API는 {"data": [...]} 봉투로 응답하지만 OpenAPI 스펙에는 배열로 선언되어 있어
    두 형태를 모두 허용한다. 그 외(null, 키 없음 등)는 0건으로 취급한다.
    """
    if isinstance(payload, dict):
        payload = payload.get(LIST_RESPONSE_DATA_KEY)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _parse_create_on(value: Any) -> datetime | None:
    """변경 일시 문자열을 파싱한다. 알려진 형식이 아니면 None 을 반환한다."""
    if not isinstance(value, str):
        return None
    for candidate in CREATE_ON_FORMATS:
        try:
            return datetime.strptime(value, candidate)
        except ValueError:
            continue
    return None


def _as_sortable_id(value: Any) -> int:
    """레코드 ID를 정렬 가능한 정수로 변환한다. 변환할 수 없으면 -1 을 반환한다."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _recency_key(record: dict[str, Any]) -> tuple[bool, datetime, str, int]:
    """최신순 정렬 키 — create_on 파싱 성공 건이 우선하고, 실패 시 문자열·id 순으로 대체한다."""
    create_on = record.get("create_on")
    parsed = _parse_create_on(create_on)
    return (
        parsed is not None,
        parsed or datetime.min,
        create_on if isinstance(create_on, str) else "",
        _as_sortable_id(record.get("id")),
    )


def _sort_by_recency(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """변경 이력 목록을 최신순으로 정렬한다 (목록 API의 정렬 순서를 신뢰하지 않는다)."""
    return sorted(records, key=_recency_key, reverse=True)


def _strip_excluded_fields(detail: dict[str, Any]) -> dict[str, Any]:
    """상세 응답에서 반환 대상이 아닌 필드(old 등)를 제거한다."""
    return {
        key: value
        for key, value in detail.items()
        if key not in EXCLUDED_DETAIL_FIELDS
    }


def _error_response(message: str) -> str:
    """조회 실패·되묻기 유도 응답을 생성한다."""
    return json.dumps(
        {"found": False, "total_count": 0, "message": message}, ensure_ascii=False
    )


def _not_found_response() -> str:
    """변경 이력이 0건일 때의 응답을 생성한다."""
    return _error_response(NOT_FOUND_MESSAGE)


def _found_response(
    total_count: int, record_id: Any, detail: dict[str, Any], notice: str | None
) -> str:
    """변경 이력 상세를 표준 응답 봉투에 담아 생성한다."""
    return json.dumps(
        {
            "found": True,
            "total_count": total_count,
            "notice": notice,
            "diff": {"id": record_id, **_strip_excluded_fields(detail)},
        },
        ensure_ascii=False,
    )


async def _get_diff(
    client: DiffClient,
    settings: Settings,
    resource: ResourceSpec,
    filter_value: str,
    start_date: str,
    end_date: str,
) -> str:
    """WAS/WEB 공통 변경 이력 조회 흐름 (설계서 3.1절)."""
    record_id: Any = None
    try:
        value = (filter_value or "").strip()
        if not value:
            return _error_response(resource.missing_filter_message)

        params = _normalize_date_range(start_date, end_date, settings.date_padding_days)
        params[resource.filter_key] = value

        records = _extract_records(await client.list_diffs(resource, params))
        if not records:
            return _not_found_response()

        total_count = len(records)
        latest = _sort_by_recency(records)[0]
        record_id = latest.get("id")

        detail = await client.get_diff_detail(resource, record_id)

        notice = None
        if total_count > 1:
            notice = MULTIPLE_RESULT_NOTICE_TEMPLATE.format(
                total_count=total_count, create_on=latest.get("create_on")
            )
        return _found_response(total_count, record_id, detail, notice)
    except ValueError as exc:
        # 입력 검증 실패(날짜 형식 등) — API 호출 실패가 아니므로 사유를 그대로 전달한다.
        return _error_response(str(exc))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == httpx.codes.NOT_FOUND and record_id is not None:
            return _error_response(
                DETAIL_NOT_FOUND_MESSAGE_TEMPLATE.format(record_id=record_id)
            )
        return _error_response(REQUEST_FAILED_MESSAGE_TEMPLATE.format(error=exc))
    except Exception as exc:
        return _error_response(REQUEST_FAILED_MESSAGE_TEMPLATE.format(error=exc))


def create_server() -> MCPServer:
    """MCPServer 서버를 생성하고 WAS/WEB 변경 이력 조회 도구를 등록한다."""
    mcp = MCPServer(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    settings = Settings()
    diff_client = DiffClient(settings)

    @mcp.tool(description=WEB_TOOL_DESCRIPTION)
    async def get_diff_web(
        host_id: str, start_date: str = "", end_date: str = ""
    ) -> str:
        """WEB 서버 설정(http.m) 변경 내역을 조회한다."""
        return await _get_diff(
            client=diff_client,
            settings=settings,
            resource=WEB_RESOURCE,
            filter_value=host_id,
            start_date=start_date,
            end_date=end_date,
        )

    @mcp.tool(description=WAS_TOOL_DESCRIPTION)
    async def get_diff_was(
        domain_id: str, start_date: str = "", end_date: str = ""
    ) -> str:
        """WAS 도메인 설정(domain.xml) 변경 내역을 조회한다."""
        return await _get_diff(
            client=diff_client,
            settings=settings,
            resource=WAS_RESOURCE,
            filter_value=domain_id,
            start_date=start_date,
            end_date=end_date,
        )

    return mcp


def main() -> None:
    """MCP 서버를 stdio 전송 방식으로 실행한다."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
