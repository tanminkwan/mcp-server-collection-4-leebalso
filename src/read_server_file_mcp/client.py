"""파일 읽기 명령 API HTTP 클라이언트 모듈."""

from __future__ import annotations

from typing import Any

import httpx

from read_server_file_mcp.config import (
    AGENT_CONDITION_PARAM,
    AGENT_LIST_KEY,
    AGENT_VALUE_KEY,
    CREATE_COMMAND_TYPE_KEY,
    CREATE_PARAMETERS_KEY,
    CREATE_TARGET_AGENT_KEY,
    READ_FILE_COMMAND_TYPE_ID,
    RESULT_COMMAND_ID_PARAM,
    Settings,
    build_agent_condition,
)


class ReadServerFileClient:
    """에이전트 조회·명령 생성·결과 조회 API와 통신하는 HTTP 클라이언트.

    Settings 를 주입받아 인증·SSL 설정을 처리한다. 응답은 가공하지 않고 그대로 반환한다
    (분기·판단은 서버 계층의 책임이다). 단, 에이전트 조회만은 범용 모델 API의 봉투
    ({"list": [{"pk":..., "value":...}]})에서 agent_id 목록을 꺼내 반환한다.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- public API -----------------------------------------------------------

    async def find_agent_ids(self, host_id: str) -> list[str]:
        """host_id 에 등록된 agent_id 목록을 조회한다 (없으면 빈 리스트)."""
        payload = await self._get(
            self._settings.agent_lookup_url,
            params={AGENT_CONDITION_PARAM: build_agent_condition(host_id)},
        )
        return self._extract_agent_ids(payload)

    async def create_read_file_command(
        self, agent_id: str, file_path: str
    ) -> dict[str, Any]:
        """대상 에이전트에 절대 경로 파일 읽기 명령을 생성하고 command_id 를 받는다.

        parameters 는 객체가 아닌 '경로 문자열' 로 보내야 한다 — 에이전트의
        ReadFullPathFile 이 additional_params 를 경로 문자열 그대로 해석하기 때문이다.
        """
        payload = {
            CREATE_COMMAND_TYPE_KEY: READ_FILE_COMMAND_TYPE_ID,
            CREATE_TARGET_AGENT_KEY: [agent_id],
            CREATE_PARAMETERS_KEY: file_path,
        }
        return await self._post(self._settings.create_url, payload)

    async def get_command_result(self, command_id: str) -> dict[str, Any]:
        """command_id 로 명령 실행 결과를 조회한다."""
        return await self._get(
            self._settings.result_url,
            params={RESULT_COMMAND_ID_PARAM: command_id},
        )

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _extract_agent_ids(payload: Any) -> list[str]:
        """조회 응답 봉투에서 agent_id 목록을 꺼낸다 (빈 값·형식 이상 항목은 제외)."""
        if not isinstance(payload, dict):
            return []
        rows = payload.get(AGENT_LIST_KEY)
        if not isinstance(rows, list):
            return []
        return [
            row[AGENT_VALUE_KEY]
            for row in rows
            if isinstance(row, dict) and isinstance(row.get(AGENT_VALUE_KEY), str)
            and row[AGENT_VALUE_KEY]
        ]

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
