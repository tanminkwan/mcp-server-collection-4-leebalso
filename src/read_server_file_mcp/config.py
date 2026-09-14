"""환경변수 기반 설정 관리 모듈."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

# API 엔드포인트 경로
COMMAND_CREATE_PATH = "/api/v1/command_master/create"
COMMAND_RESULT_PATH = "/api/v1/command_master/result"
AGENT_LOOKUP_PATH = "/api/v1/model/column_all/{table_column}"

# host_id → agent_id 조회 대상 테이블/컬럼 (ag_agent 가 두 값을 함께 보유한다)
AGENT_TABLE = "ag_agent"
AGENT_ID_COLUMN = "agent_id"
HOST_ID_COLUMN = "host_id"

# 범용 모델 조회 API의 조건 파라미터 규격
AGENT_CONDITION_PARAM = "condition"
AGENT_LOOKUP_OPERATOR = "eql"  # 완전 일치
CONDITION_COLUMN_KEY = "column"
CONDITION_OPERATOR_KEY = "operator"
CONDITION_VALUE_KEY = "value"

# 조회 응답 봉투 키
AGENT_LIST_KEY = "list"
AGENT_VALUE_KEY = "value"

# 파일 읽기 명령 타입 — target_file_path/name 이 비어 있어 호출 시점에 경로를 지정할 수 있는
# 범용 타입이다. 에이전트 측 처리 클래스는 ReadFullPathFile 이며 additional_params 를
# '읽을 파일의 절대 경로 문자열' 로 해석한다.
READ_FILE_COMMAND_TYPE_ID = "COMMON.READFILE"

# 명령 생성 요청 본문 키
CREATE_COMMAND_TYPE_KEY = "command_type_id"
CREATE_TARGET_AGENT_KEY = "target_agent_id"
CREATE_PARAMETERS_KEY = "parameters"

# 결과 조회 쿼리 파라미터 및 응답 키
RESULT_COMMAND_ID_PARAM = "command_id"
RESULT_DATA_KEY = "data"
COMMAND_ID_KEY = "command_id"
ADDITIONAL_PARAMS_KEY = "additional_params"
RESULT_TEXT_KEY = "result_text"
RESULT_STATUS_KEY = "result_status"
RESULT_MESSAGE_KEY = "result_message"
COMPLITED_DATE_KEY = "complited_date"
AGENT_ID_KEY = "agent_id"
HOST_ID_KEY = "host_id"

# 절대 경로 판정 — 에이전트는 Linux/AIX 와 Windows 양쪽에서 동작한다.
POSIX_PATH_PREFIX = "/"
UNC_PATH_PREFIX = "\\\\"
WINDOWS_PATH_SEPARATORS = ("\\", "/")
PATH_TRAVERSAL_TOKEN = ".."

# 에이전트가 실패 시 result_text 에 채워 넣는 고정 문구.
# 이 값과 '완전히 일치' 할 때만 오류로 표시한다 (파일 내용에 같은 단어가 들어 있을 수 있으므로
# 부분 일치로는 판단하지 않는다).
AGENT_ERROR_SENTINELS = (
    "Error:FileNotFoundException",
    "Error:IOException",
    "Error:UnsupportedEncodingException",
    "Error:NoSuchAlgorithmException",
    "NO CHANGE",
)

# SSL 검증 기본값
DEFAULT_SSL_VERIFY = False

# HTTP 요청 타임아웃 (초)
DEFAULT_TIMEOUT = 60

# 명령 주문 후 결과 조회까지 권장 대기 시간 (초)
DEFAULT_RESULT_WAIT_SECONDS = 30

# 응답 메시지 — 필수 값 누락 시 AI Agent 가 사용자에게 되묻도록 유도한다.
MISSING_HOST_ID_MESSAGE = (
    "파일을 읽을 대상 서버의 host_id가 필요합니다. "
    "사용자에게 어느 서버(호스트/시스템)의 파일인지 확인해 주세요. "
    "추측하지 말고 되물어야 합니다."
)
MISSING_FILE_PATH_MESSAGE = (
    "읽을 파일의 경로(file_path)가 필요합니다. "
    "사용자에게 어느 위치의 어떤 파일인지 절대 경로로 확인해 주세요. "
    "추측하지 말고 되물어야 합니다."
)
MISSING_COMMAND_ID_MESSAGE = (
    "조회할 command_id가 필요합니다. "
    "먼저 request_read_server_file 도구로 파일 읽기를 주문하고 command_id를 받으세요."
)
NOT_ABSOLUTE_PATH_MESSAGE_TEMPLATE = (
    "file_path는 절대 경로여야 합니다: '{file_path}'. "
    "예) /var/log/messages, C:\\logs\\app.log"
)
PATH_TRAVERSAL_MESSAGE_TEMPLATE = (
    "file_path에 상위 디렉터리 참조('..')를 사용할 수 없습니다: '{file_path}'. "
    "에이전트가 path traversal로 차단하므로 정규화된 절대 경로를 사용하세요."
)
AGENT_NOT_FOUND_MESSAGE_TEMPLATE = (
    "host_id '{host_id}'로 등록된 에이전트를 찾을 수 없습니다. "
    "해당 서버에 에이전트가 설치되어 있지 않거나 host_id가 정확하지 않을 수 있습니다. "
    "사용자에게 서버명을 다시 확인해 주세요."
)
NO_COMMAND_ID_MESSAGE_TEMPLATE = (
    "명령은 생성되었으나 응답에서 command_id를 찾을 수 없습니다. 응답: {response}"
)
MULTIPLE_AGENT_NOTICE_TEMPLATE = (
    "host_id '{host_id}'에 에이전트가 {count}개 등록되어 있습니다. "
    "그 중 '{selected}'로 명령을 보냈습니다. (전체: {all_agents}) "
    "결과가 예상과 다르면 다른 에이전트일 수 있습니다."
)
REQUEST_ACCEPTED_NOTICE_TEMPLATE = (
    "파일 읽기에 약 {wait_seconds}초 정도 소요됩니다. "
    "사용자에게 먼저 이 소요 시간을 안내한 뒤 약 {wait_seconds}초 대기하고, "
    "그 다음 get_read_server_file_result 도구를 command_id로 호출하세요. "
    "결과가 아직 없으면 조금 더 기다렸다가 다시 조회하세요."
)
RESULT_PENDING_MESSAGE_TEMPLATE = (
    "command_id '{command_id}'의 실행 결과가 아직 도착하지 않았습니다. "
    "에이전트가 명령을 가져가 수행하는 중일 수 있습니다. "
    "약 {wait_seconds}초 더 기다린 뒤 다시 조회하세요."
)
RESULT_NOTICE = (
    "result_text는 파일 내용일 수도 있고 FileNotFound 등 오류 메시지일 수도 있습니다. "
    "둘 중 어느 쪽인지는 호출한 AI Agent가 내용을 보고 판단해야 합니다. "
    "agent_error_sentinel이 채워져 있으면 에이전트가 반환한 알려진 오류 문구와 정확히 "
    "일치한다는 뜻이며, null이어도 반드시 정상 파일 내용이라는 보장은 아닙니다. "
    "file_path는 실제로 읽으라고 지시된 파일 위치이므로 요청한 경로와 일치하는지 확인하세요."
)
CREATE_FAILED_MESSAGE_TEMPLATE = "파일 읽기 명령 생성 오류: {error}"
RESULT_FAILED_MESSAGE_TEMPLATE = "파일 읽기 결과 조회 오류: {error}"


def build_agent_condition(host_id: str) -> str:
    """host_id 완전 일치 조건을 범용 모델 조회 API 규격의 JSON 문자열로 만든다."""
    return json.dumps(
        {
            CONDITION_COLUMN_KEY: HOST_ID_COLUMN,
            CONDITION_OPERATOR_KEY: AGENT_LOOKUP_OPERATOR,
            CONDITION_VALUE_KEY: host_id,
        },
        ensure_ascii=False,
    )


class Settings:
    """파일 읽기 명령 API 접속에 필요한 설정을 환경변수에서 로드한다."""

    def __init__(self) -> None:
        load_dotenv()

        self.api_base_url = self._require("API_BASE_URL")
        self.api_bearer_token = self._require("API_BEARER_TOKEN")
        self.api_ssl_verify = self._parse_bool(
            os.getenv("API_SSL_VERIFY"), DEFAULT_SSL_VERIFY
        )
        self.api_timeout = int(os.getenv("API_TIMEOUT", str(DEFAULT_TIMEOUT)))
        self.result_wait_seconds = int(
            os.getenv(
                "READ_SERVER_FILE_RESULT_WAIT_SECONDS", str(DEFAULT_RESULT_WAIT_SECONDS)
            )
        )

    # -- derived properties --------------------------------------------------

    @property
    def create_url(self) -> str:
        return f"{self.api_base_url}{COMMAND_CREATE_PATH}"

    @property
    def result_url(self) -> str:
        return f"{self.api_base_url}{COMMAND_RESULT_PATH}"

    @property
    def agent_lookup_url(self) -> str:
        """ag_agent.agent_id 컬럼 조회 URL을 생성한다."""
        table_column = f"{AGENT_TABLE}.{AGENT_ID_COLUMN}"
        return f"{self.api_base_url}{AGENT_LOOKUP_PATH.format(table_column=table_column)}"

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
