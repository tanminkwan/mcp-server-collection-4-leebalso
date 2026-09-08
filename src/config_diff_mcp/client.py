"""WAS/WEB 설정 변경 이력 API HTTP 클라이언트 모듈."""

from __future__ import annotations

from typing import Any

import httpx

from config_diff_mcp.config import ResourceSpec, Settings


class DiffClient:
    """변경 이력 API(목록/상세)와 통신하는 HTTP 클라이언트.

    Settings 를 주입받아 인증·SSL 설정을 처리한다. 응답은 가공하지 않고 그대로 반환한다
    (필드 제외·정렬·분기 등의 판단은 서버 계층의 책임이다).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- public API -----------------------------------------------------------

    async def list_diffs(
        self, resource: ResourceSpec, params: dict[str, Any]
    ) -> Any:
        """일자 구간·대상 식별자 조건으로 변경 이력 목록을 조회한다."""
        return await self._get(self._settings.list_url(resource), params=params)

    async def get_diff_detail(
        self, resource: ResourceSpec, record_id: str | int
    ) -> dict[str, Any]:
        """변경 이력 ID로 설정 전문 및 Unified Diff 상세를 조회한다."""
        return await self._get(self._settings.detail_url(resource, record_id))

    # -- helpers --------------------------------------------------------------

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """API에 GET 요청을 보내고 JSON 응답을 반환한다."""
        async with httpx.AsyncClient(
            verify=self._settings.api_ssl_verify,
            timeout=self._settings.api_timeout,
        ) as http:
            response = await http.get(
                url,
                params=params,
                headers=self._settings.auth_header,
            )
            response.raise_for_status()
            return response.json()
