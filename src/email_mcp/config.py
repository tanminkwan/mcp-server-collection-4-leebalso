"""환경변수 기반 설정 관리 모듈."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

from mcp_common.config import load_max_response_bytes

# API 엔드포인트 경로
EMAIL_SEND_PATH = "/api/v1/email/send"
EMAIL_SEND_MARKDOWN_PATH = "/api/v1/email/send_markdown"

# SSL 검증 기본값
DEFAULT_SSL_VERIFY = False

# HTTP 요청 타임아웃 (초)
DEFAULT_TIMEOUT = 60

# 발신인 기본 표시 이름
DEFAULT_SENDER_NAME = "MCP Email"


class Settings:
    """EmailApi 접속에 필요한 설정을 환경변수에서 로드한다."""

    def __init__(self) -> None:
        load_dotenv()

        self.api_base_url = self._require("API_BASE_URL")
        self.api_bearer_token = self._require("API_BEARER_TOKEN")
        self.api_ssl_verify = self._parse_bool(
            os.getenv("API_SSL_VERIFY"), DEFAULT_SSL_VERIFY
        )
        self.api_timeout = int(os.getenv("API_TIMEOUT", str(DEFAULT_TIMEOUT)))
        self.recipient_mapping: dict[str, str] = self._parse_mapping(
            os.getenv("EMAIL_RECIPIENT_MAPPING", "")
        )
        # AI Agent 에게 돌려줄 응답의 최대 크기 — 모든 MCP 서버가 공유하는 한도.
        self.max_response_bytes = load_max_response_bytes()

    # -- derived properties --------------------------------------------------

    @property
    def email_send_url(self) -> str:
        return f"{self.api_base_url}{EMAIL_SEND_PATH}"

    @property
    def email_send_markdown_url(self) -> str:
        return f"{self.api_base_url}{EMAIL_SEND_MARKDOWN_PATH}"

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

    @staticmethod
    def _parse_mapping(value: str) -> dict[str, str]:
        if not value:
            return {}
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

        # 쉼표 구분 및 콜론(이름:이메일) 형태의 문자열 파싱 (Fallback)
        mapping = {}
        for pair in value.split(","):
            pair = pair.strip()
            if ":" in pair:
                name, email = pair.split(":", 1)
                mapping[name.strip()] = email.strip()
        return mapping

