"""환경변수 기반 설정 관리 모듈."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# API 엔드포인트 경로
WAS_LIST_PATH = "/diff_data/was/list"
WAS_DETAIL_PATH = "/diff_data/was/{id}"
WEB_LIST_PATH = "/diff_data/web/list"
WEB_DETAIL_PATH = "/diff_data/web/{id}"

# 목록 조회 필터 파라미터명
WAS_FILTER_KEY = "domain_id"
WEB_FILTER_KEY = "host_id"

# 대상 설정 파일명 — 사용자가 WAS/WEB 대신 파일명으로 지칭하는 경우의 별칭이기도 하다.
WAS_CONFIG_FILE_NAME = "domain.xml"
WEB_CONFIG_FILE_NAME = "http.m"

# 날짜 입출력 형식
DATE_FORMAT = "%Y-%m-%d"

# create_on 파싱 시도 형식 — 실제 응답 포맷이 스펙에 명시되어 있지 않아 후보를 순차 시도한다.
CREATE_ON_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d",
)

# 단일 일자 지정 시 앞뒤로 확장할 일수 기본값
DEFAULT_DATE_PADDING_DAYS = 1

# 목록 응답 봉투 키 — 실제 API는 {"data": [...]} 형태로 응답한다
# (OpenAPI 스펙에는 배열로 선언되어 있어 두 형태를 모두 허용한다).
LIST_RESPONSE_DATA_KEY = "data"

# 상세 응답에서 제외할 필드 — old(이전 설정 전문)는 new와 unified_diff로 복원 가능하므로
# AI Agent의 컨텍스트 토큰을 낭비하지 않도록 반환하지 않는다.
EXCLUDED_DETAIL_FIELDS = ("old",)

# SSL 검증 기본값
DEFAULT_SSL_VERIFY = False

# HTTP 요청 타임아웃 (초)
DEFAULT_TIMEOUT = 60

# 응답 메시지
NOT_FOUND_MESSAGE = "존재하지 않습니다."
MULTIPLE_RESULT_NOTICE_TEMPLATE = (
    "전체 {total_count}건의 변경 내역이 있습니다. "
    "그 중 가장 최근({create_on}) 1건만 반환합니다."
)
DETAIL_NOT_FOUND_MESSAGE_TEMPLATE = (
    "해당 변경 이력 상세를 찾을 수 없습니다. (id={record_id})"
)
INVALID_DATE_MESSAGE_TEMPLATE = (
    "날짜는 {date_format} 형식(예: 2026-08-11)이어야 합니다: '{value}'"
)
REQUEST_FAILED_MESSAGE_TEMPLATE = "변경 이력 조회 오류: {error}"

# 대상 식별자 누락 시 AI Agent가 사용자에게 되묻도록 유도하는 메시지
MISSING_HOST_ID_MESSAGE = (
    "조회할 WEB 서버의 host_id가 필요합니다. "
    f"사용자에게 어느 서버(호스트)의 {WEB_CONFIG_FILE_NAME} 변경 내역인지 확인해 주세요."
)
MISSING_DOMAIN_ID_MESSAGE = (
    "조회할 WAS 도메인 ID(domain_id)가 필요합니다. "
    f"사용자에게 어느 WAS 도메인의 {WAS_CONFIG_FILE_NAME} 변경 내역인지 확인해 주세요. "
    "WAS는 서버명(host_id)으로는 조회할 수 없습니다."
)


@dataclass(frozen=True)
class ResourceSpec:
    """변경 이력 조회 대상(WAS/WEB) 한 종류의 정의.

    새로운 대상이 추가되어도 이 스펙 인스턴스와 얇은 도구 래퍼만 추가하면 되므로
    공통 조회 흐름 코드는 수정할 필요가 없다 (개방-폐쇄 원칙).
    """

    name: str
    list_path: str
    detail_path: str
    filter_key: str
    config_file_name: str
    missing_filter_message: str


WAS_RESOURCE = ResourceSpec(
    name="was",
    list_path=WAS_LIST_PATH,
    detail_path=WAS_DETAIL_PATH,
    filter_key=WAS_FILTER_KEY,
    config_file_name=WAS_CONFIG_FILE_NAME,
    missing_filter_message=MISSING_DOMAIN_ID_MESSAGE,
)

WEB_RESOURCE = ResourceSpec(
    name="web",
    list_path=WEB_LIST_PATH,
    detail_path=WEB_DETAIL_PATH,
    filter_key=WEB_FILTER_KEY,
    config_file_name=WEB_CONFIG_FILE_NAME,
    missing_filter_message=MISSING_HOST_ID_MESSAGE,
)


class Settings:
    """변경 이력 API 접속에 필요한 설정을 환경변수에서 로드한다."""

    def __init__(self) -> None:
        load_dotenv()

        self.api_base_url = self._require("API_BASE_URL")
        self.api_bearer_token = self._require("API_BEARER_TOKEN")
        self.api_ssl_verify = self._parse_bool(
            os.getenv("API_SSL_VERIFY"), DEFAULT_SSL_VERIFY
        )
        self.api_timeout = int(os.getenv("API_TIMEOUT", str(DEFAULT_TIMEOUT)))
        self.date_padding_days = int(
            os.getenv("DIFF_DATE_PADDING_DAYS", str(DEFAULT_DATE_PADDING_DAYS))
        )

    # -- derived properties --------------------------------------------------

    def list_url(self, resource: ResourceSpec) -> str:
        """대상 리소스의 변경 이력 목록 조회 URL을 생성한다."""
        return f"{self.api_base_url}{resource.list_path}"

    def detail_url(self, resource: ResourceSpec, record_id: str | int) -> str:
        """대상 리소스의 변경 이력 상세 조회 URL을 생성한다."""
        return f"{self.api_base_url}{resource.detail_path.format(id=record_id)}"

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
