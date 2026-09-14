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

# mdcontent 목록 조회 파라미터
SEARCH_TAGS_PARAM = "search_tags"
MAX_PARAM = "max"
MDCONTENT_LIST_MAX = 1

# 응답 봉투 키
DATA_KEY = "data"
CONTENT_ID_KEY = "content_id"

# 입력 검증 규칙 — date 는 yyyymmdd(8자리), time 은 hhmiss(6자리) 숫자여야 한다.
DATE_PATTERN = r"^\d{8}$"
TIME_PATTERN = r"^\d{6}$"
# WAS 인스턴스 ID 는 반드시 이 토큰을 포함한다 (예: ONL_MS12).
WAS_INSTANCE_TOKEN = "_MS"

# 요청 본문 키
PAYLOAD_DATE_KEY = "date"
PAYLOAD_HOST_ID_KEY = "host_id"
PAYLOAD_TIME_FROM_KEY = "time_from"
PAYLOAD_TIME_TO_KEY = "time_to"
PAYLOAD_WAS_INSTANCE_ID_KEY = "was_instance_id"

# 응답 메시지 — 입력 검증 실패
INVALID_DATE_MESSAGE = "오류: date는 yyyymmdd 형식(8자리 숫자)이어야 합니다."
INVALID_TIME_MESSAGE = "오류: time_from과 time_to는 hhmiss 형식(6자리 숫자)이어야 합니다."
INVALID_TIME_ORDER_MESSAGE = "오류: time_from 값은 time_to 보다 작아야 합니다."
INVALID_WAS_INSTANCE_MESSAGE = (
    f"오류: was_instance_id는 반드시 '{WAS_INSTANCE_TOKEN}' 형태를 포함해야 합니다."
)

# 응답 메시지 — 조회 결과 및 오류
MDCONTENT_NOT_FOUND_MESSAGE_TEMPLATE = (
    "command_id '{command_id}'에 해당하는 mdcontent를 찾을 수 없습니다. "
    "(아직 생성 중일 수 있습니다.)"
)
NO_CONTENT_ID_MESSAGE_TEMPLATE = (
    "목록 조회 결과에서 content_id를 찾을 수 없습니다. 응답: {response}"
)
REQUEST_FAILED_MESSAGE_TEMPLATE = "로그 추출 요청 오류: {error}"
RESULT_FAILED_MESSAGE_TEMPLATE = "로그 추출 결과 조회 오류: {error}"


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
