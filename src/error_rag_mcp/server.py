"""MCP 서버 — stdio 전송 방식으로 오류/조치 RAG 검색 및 등록 도구를 제공한다."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from error_rag_mcp.client import RagClient
from error_rag_mcp.config import (
    CONTENT_COMPOSE_TEMPLATE,
    LOCATION_COMPOSE_TEMPLATE,
    MAX_ERROR_KEYWORD_COUNT,
    MAX_ERROR_SUMMARY_LENGTH,
    REPORT_TEMPLATE,
    Settings,
    TEXT_MATCHING_SEARCH_METHOD,
    VECTOR_SEARCH_METHOD,
)
from mcp_common.response_limit import limit_response_size

SERVER_NAME = "error-rag-mcp"
SERVER_INSTRUCTIONS = (
    "오류/장애 발생 시 과거 유사 사례와 조치 방법을 RAG 서비스에서 검색하고(search_similar_error), "
    "조치 완료 후 오류 및 조치 결과를 RAG 서비스에 등록(register_error_resolution)하는 MCP 서버입니다. "
    "'이 오류 예전에도 있었어?', '비슷한 장애 사례 찾아줘'와 같은 요청에는 search_similar_error를, "
    "'이 오류 조치 내용을 기록해줘', '방금 처리한 장애 등록해줘'와 같은 요청에는 "
    "register_error_resolution을 사용하세요. 전형적인 흐름은 오류 탐지 → 로그 요약 → "
    "search_similar_error로 과거 사례 확인 → 조치 수행 → register_error_resolution으로 결과 등록 "
    "순서이며, 두 도구 호출 시 동일한 error_keyword를 재사용하면 다음에 같은 오류가 발생했을 때 "
    "이번에 등록한 사례도 검색되어 지식이 누적됩니다."
)


def create_rag_client() -> RagClient:
    """Settings 를 로드하여 RagClient 를 생성한다."""
    return RagClient(Settings())


def _compose_content(error_summary: str, error_keyword: list[str]) -> str:
    """error_summary와 error_keyword 목록을 결합해 검색 가능한 content를 생성한다."""
    keywords = ", ".join(error_keyword)
    return CONTENT_COMPOSE_TEMPLATE.format(error_summary=error_summary, keywords=keywords)


def _compose_location(host_id: str, was_instance_id: str) -> str:
    """host_id와 was_instance_id를 연결해 오류 발생 위치 문자열을 생성한다."""
    return LOCATION_COMPOSE_TEMPLATE.format(
        host_id=host_id, was_instance_id=was_instance_id
    )


def _compose_report(
    error_occurred_at: str,
    error_location: str,
    error_content: str,
    action_taken_at: str,
    actor: str,
    action_content: str,
) -> str:
    """표준 오류 및 조치 보고서 양식(extended_content)을 생성한다."""
    return REPORT_TEMPLATE.format(
        error_occurred_at=error_occurred_at,
        error_location=error_location,
        error_content=error_content,
        action_taken_at=action_taken_at,
        actor=actor,
        action_content=action_content,
    )


def _dedupe_by_id(*result_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """여러 검색 결과 목록을 순서를 유지하며 id 기준으로 distinct 병합한다."""
    seen: set[Any] = set()
    merged: list[dict[str, Any]] = []
    for results in result_lists:
        for item in results:
            item_id = item.get("id")
            if item_id in seen:
                continue
            seen.add(item_id)
            merged.append(item)
    return merged


def create_server() -> MCPServer:
    """MCPServer 서버를 생성하고 검색/등록 도구를 등록한다."""
    mcp = MCPServer(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    settings = Settings()
    rag_client = RagClient(settings)

    @mcp.tool()
    @limit_response_size(settings)
    async def search_similar_error(error_summary: str, error_keyword: str) -> str:
        """과거 동일/유사 오류 사례와 조치 방법을 RAG 서비스에서 검색합니다. 조치를 시작하기 전에
        먼저 호출해서 이미 알려진 해결 방법이 있는지 확인하세요. 오류 요약으로 벡터(의미) 검색을,
        오류 코드 등 핵심 키워드로 텍스트 매칭(정확 일치) 검색을 함께 수행하여 결과를 병합·중복
        제거해 반환합니다. 결과가 빈 배열(`[]`)이면 과거 유사 사례가 없다는 뜻입니다. 조치 방법
        판단은 이 결과를 참고해 호출자(AI Agent)가 직접 수행하세요.

        Args:
            error_summary: 오류 내용 요약 (300자 이내). 벡터 검색 쿼리로 사용됩니다.
            error_keyword: 오류 코드, 예외 클래스명 등 정확히 일치해야 의미 있는 핵심 식별
                키워드. 텍스트 매칭 검색 쿼리로 사용됩니다. 명확한 키워드가 없으면 빈 문자열로
                두세요 — 이 경우 텍스트 매칭 검색은 건너뛰고 벡터 검색 결과만 반환합니다(빈
                키워드로 텍스트 매칭 검색을 하면 무관한 결과가 섞여 들어갑니다).
        """
        try:
            vector_results = await rag_client.search(
                query=error_summary,
                search_method=VECTOR_SEARCH_METHOD,
                limit=settings.vector_search_limit,
            )
            text_matching_results = []
            if error_keyword and error_keyword.strip():
                text_matching_results = await rag_client.search(
                    query=error_keyword,
                    search_method=TEXT_MATCHING_SEARCH_METHOD,
                    limit=settings.text_matching_limit,
                )
            merged = _dedupe_by_id(vector_results, text_matching_results)
            return json.dumps(merged, ensure_ascii=False)
        except Exception as exc:
            return f"오류 검색 오류: {exc}"

    @mcp.tool()
    @limit_response_size(settings)
    async def register_error_resolution(
        error_summary: str,
        error_keyword: list[str],
        error_occurred_at: str,
        host_id: str,
        was_instance_id: str,
        error_content: str,
        action_taken_at: str,
        actor: str,
        action_content: str,
    ) -> str:
        """오류 및 조치 결과를 표준 보고서 형식으로 RAG 서비스에 등록합니다. 조치가 끝난 뒤에만
        호출하세요 — 조치 전이라면 search_similar_error로 먼저 과거 사례를 확인해야 합니다. 이
        도구를 호출하면 다음에 동일/유사 오류 발생 시 재활용할 수 있는 지식이 축적됩니다.

        Args:
            error_summary: 오류 내용 요약 (300자 이내). 향후 벡터/텍스트 매칭 검색 대상이 됩니다.
            error_keyword: 오류 코드 등 핵심 식별 키워드 목록 (1개 이상, 최대 3개, 빈 문자열
                불가). search_similar_error에서 사용한 키워드와 동일하게 넣으면 이번에 등록한
                사례가 다음 검색에서도 재현되어 지식이 누적됩니다. 텍스트 매칭 검색으로 이 사례를
                찾을 수 있도록 content에 결합되어 저장됩니다.
            error_occurred_at: 오류 발생일시
            host_id: 오류가 발생한 호스트 ID. '서버' 또는 '시스템'이라고도 부릅니다. 이 도구를
                호출하는 AI Agent가 오류를 탐지·분석하는 과정에서 이미 파악하고 있는 값을 그대로
                전달하세요(예: extract_error_log_mcp로 로그를 조회할 때 사용한 host_id와 동일한
                값). 확인할 수 없다면 빈 문자열로 두지 말고 알고 있는 범위에서 최대한 구체적으로
                전달하세요.
            was_instance_id: 오류가 발생한 WAS 인스턴스 ID. 보통 문자열 안에 '_MS'를 포함합니다
                (예: 'ONL_MS12'). 'OOO 서버의 XXX'처럼 표현되는 경우 XXX가 WAS 인스턴스 ID입니다.
                host_id와 마찬가지로 AI Agent가 이미 파악하고 있는 값을 그대로 전달하세요.
            error_content: 오류 내용 (상세)
            action_taken_at: 조치일시
            actor: 조치자
            action_content: 조치 내용
        """
        try:
            if len(error_summary) > MAX_ERROR_SUMMARY_LENGTH:
                raise ValueError(
                    f"error_summary는 {MAX_ERROR_SUMMARY_LENGTH}자를 초과할 수 없습니다."
                )
            if (
                not error_keyword
                or len(error_keyword) > MAX_ERROR_KEYWORD_COUNT
                or any(not keyword.strip() for keyword in error_keyword)
            ):
                raise ValueError(
                    f"error_keyword는 빈 문자열 없이 1개 이상 {MAX_ERROR_KEYWORD_COUNT}개 "
                    "이하로 지정해야 합니다."
                )

            content = _compose_content(error_summary, error_keyword)
            error_location = _compose_location(
                host_id=host_id, was_instance_id=was_instance_id
            )
            extended_content = _compose_report(
                error_occurred_at=error_occurred_at,
                error_location=error_location,
                error_content=error_content,
                action_taken_at=action_taken_at,
                actor=actor,
                action_content=action_content,
            )
            result = await rag_client.register(
                content=content, extended_content=extended_content
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return f"오류 조치 결과 등록 오류: {exc}"

    return mcp


def main() -> None:
    """MCP 서버를 stdio 전송 방식으로 실행한다."""
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
