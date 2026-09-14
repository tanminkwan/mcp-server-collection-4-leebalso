"""환경변수 기반 설정 관리 모듈."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from mcp_common.config import load_max_response_bytes

# API 엔드포인트 경로
RAG_SEARCH_PATH = "/api/rag/search"
RAG_KNOWLEDGE_PATH = "/api/rag/knowledge"

# 검색 방식
VECTOR_SEARCH_METHOD = "vector"
TEXT_MATCHING_SEARCH_METHOD = "text_matching"

# SSL 검증 기본값
DEFAULT_SSL_VERIFY = False

# HTTP 요청 타임아웃 (초)
DEFAULT_TIMEOUT = 60

# 검색 결과 개수 기본값
DEFAULT_VECTOR_SEARCH_LIMIT = 3
DEFAULT_TEXT_MATCHING_LIMIT = 2

# 등록 시 source 기본값
DEFAULT_SOURCE = "error-resolution-report"

# 오류 요약 최대 길이 (문자 수 기준)
MAX_ERROR_SUMMARY_LENGTH = 300

# 오류 키워드 최대 개수
MAX_ERROR_KEYWORD_COUNT = 3

# content 결합 템플릿 — error_summary와 error_keyword 목록을 결합해 검색 가능한 content를 생성한다.
# text_matching 검색은 content 필드만 검색하므로(extended_content는 검색 대상 아님), 키워드가
# 항상 content에 포함되도록 서버가 강제로 결합한다.
CONTENT_COMPOSE_TEMPLATE = "{error_summary} [{keywords}]"

# 오류 및 조치 보고서 표준 양식 (extended_content)
# 각 필드를 "### N. 필드명" 대목차로 분리한다 — 조치 내용 등에 마크다운이 포함되어 있어도
# bullet 한 줄에 값이 이어 붙는 형태(- 필드명: 값)가 아니므로 문서 구조가 깨지지 않는다.
REPORT_TEMPLATE = (
    "# 오류 및 조치 보고서\n"
    "\n"
    "### 1. 오류 발생일시\n"
    "{error_occurred_at}\n"
    "\n"
    "### 2. 오류 발생 위치\n"
    "{error_location}\n"
    "\n"
    "### 3. 오류 내용\n"
    "{error_content}\n"
    "\n"
    "### 4. 조치일시\n"
    "{action_taken_at}\n"
    "\n"
    "### 5. 조치자\n"
    "{actor}\n"
    "\n"
    "### 6. 조치 내용\n"
    "{action_content}"
)

# 오류 발생 위치(extended_content 2번 항목) 결합 템플릿 — host_id와 was_instance_id를 연결해
# 하나의 위치 표시 문자열로 만든다.
LOCATION_COMPOSE_TEMPLATE = "{host_id} / {was_instance_id}"


class Settings:
    """llm-agent RAG API 접속에 필요한 설정을 환경변수에서 로드한다."""

    def __init__(self) -> None:
        load_dotenv()

        self.api_base_url = self._require("RAG_API_BASE_URL")
        self.api_bearer_token = os.getenv("RAG_API_BEARER_TOKEN") or None
        self.api_ssl_verify = self._parse_bool(
            os.getenv("RAG_API_SSL_VERIFY"), DEFAULT_SSL_VERIFY
        )
        self.api_timeout = int(os.getenv("RAG_API_TIMEOUT", str(DEFAULT_TIMEOUT)))
        self.collection_name = self._require("RAG_COLLECTION_NAME")
        self.domain_id = int(self._require("RAG_DOMAIN_ID"))
        self.vector_search_limit = int(
            os.getenv("RAG_VECTOR_SEARCH_LIMIT", str(DEFAULT_VECTOR_SEARCH_LIMIT))
        )
        self.text_matching_limit = int(
            os.getenv("RAG_TEXT_MATCHING_LIMIT", str(DEFAULT_TEXT_MATCHING_LIMIT))
        )
        self.source = os.getenv("RAG_SOURCE", DEFAULT_SOURCE)
        # AI Agent 에게 돌려줄 응답의 최대 크기 — 모든 MCP 서버가 공유하는 한도.
        self.max_response_bytes = load_max_response_bytes()

    # -- derived properties --------------------------------------------------

    @property
    def search_url(self) -> str:
        return f"{self.api_base_url}{RAG_SEARCH_PATH}"

    @property
    def knowledge_url(self) -> str:
        return f"{self.api_base_url}{RAG_KNOWLEDGE_PATH}"

    @property
    def auth_header(self) -> dict[str, str]:
        if not self.api_bearer_token:
            return {}
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
