"""환경변수 기반 설정 관리 모듈."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from mcp_common.config import load_max_response_bytes

# API 엔드포인트 경로
EXTRACT_LOG_PATH = "/api/v1/command_master/extract_log"
MDCONTENT_LIST_PATH = "/api/v1/knowledge/mdcontent/list"
MDCONTENT_GET_PATH = "/api/v1/knowledge/mdcontent/{content_id}"

# SSL 검증 기본값
DEFAULT_SSL_VERIFY = False

# HTTP 요청 타임아웃 (초)
DEFAULT_TIMEOUT = 60


class Settings:
    """API 접속에 필요한 설정을 환경변수에서 로드한다."""

    def __init__(self) -> None:
        load_dotenv()

        self.api_base_url = self._require("API_BASE_URL")
        self.api_bearer_token = self._require("API_BEARER_TOKEN")
        self.api_ssl_verify = self._parse_bool(
            os.getenv("API_SSL_VERIFY"), DEFAULT_SSL_VERIFY
        )
        self.api_timeout = int(os.getenv("API_TIMEOUT", str(DEFAULT_TIMEOUT)))
        # AI Agent 에게 돌려줄 응답의 최대 크기 — 모든 MCP 서버가 공유하는 한도.
        self.max_response_bytes = load_max_response_bytes()

    # -- derived properties --------------------------------------------------

    @property
    def extract_log_url(self) -> str:
        return f"{self.api_base_url}{EXTRACT_LOG_PATH}"

    @property
    def mdcontent_list_url(self) -> str:
        return f"{self.api_base_url}{MDCONTENT_LIST_PATH}"

    def get_mdcontent_url(self, content_id: str | int) -> str:
        return f"{self.api_base_url}{MDCONTENT_GET_PATH.format(content_id=content_id)}"

    @property
    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_bearer_token}"}

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _require(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise ValueError(f"환경변수 {name}이(가) 설정되지 않았습니다.")
        return value

    @staticmethod
    def _parse_bool(value: str | None, default: bool) -> bool:
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes")
