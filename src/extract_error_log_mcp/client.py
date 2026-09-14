"""Extract Error Log HTTP 클라이언트 모듈."""

from __future__ import annotations

from typing import Any

import httpx

from extract_error_log_mcp.config import (
    MAX_PARAM,
    MDCONTENT_LIST_MAX,
    SEARCH_TAGS_PARAM,
    Settings,
)


class ExtractLogClient:
    """API와 통신하는 HTTP 클라이언트.

    Settings 를 주입받아 인증·SSL 설정을 처리한다.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- public API -----------------------------------------------------------

    async def request_extract_log(self, payload: dict[str, Any]) -> dict[str, Any]:
        """로그 추출을 요청하고 command_id 등을 포함한 응답을 반환한다."""
        return await self._post(self._settings.extract_log_url, payload)

    async def get_mdcontent_list(self, search_tags: str) -> dict[str, Any]:
        """search_tags로 mdcontent 목록을 조회한다."""
        params = {
            SEARCH_TAGS_PARAM: search_tags,
            MAX_PARAM: MDCONTENT_LIST_MAX,
        }
        return await self._get(self._settings.mdcontent_list_url, params=params)

    async def get_mdcontent(self, content_id: str | int) -> dict[str, Any]:
        """content_id로 mdcontent 상세를 조회한다."""
        url = self._settings.get_mdcontent_url(content_id)
        return await self._get(url)

    # -- helpers --------------------------------------------------------------

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """API에 POST 요청을 보내고 JSON 응답을 반환한다."""
        async with httpx.AsyncClient(
            verify=self._settings.api_ssl_verify,
            timeout=self._settings.api_timeout,
        ) as http:
            response = await http.post(
                url,
                json=payload,
                headers=self._settings.auth_header,
            )
            response.raise_for_status()
            return response.json()

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
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
