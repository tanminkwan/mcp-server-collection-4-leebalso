# 아키텍처 정의

## 개요

이 저장소는 **stdio 전송 방식**의 독립적인 MCP(Model Context Protocol) 서버 4개로 구성된
컬렉션이다. 각 서버는 서로 의존하지 않으며, 모두 `config.py`(환경변수 기반 설정) →
`client.py`(HTTP 클라이언트) → `server.py`(MCP 도구 등록 및 엔트리포인트) 3계층 구조를
공유한다.

| 서버 | 패키지 | 역할 |
|------|--------|------|
| Email MCP | `email_mcp` | 리발소 EmailApi를 통해 HTML/Markdown 이메일 발송 |
| Extract Error Log MCP | `extract_error_log_mcp` | 서버 에러 로그 추출 요청 및 결과(마크다운) 조회 |
| Error RAG MCP | `error_rag_mcp` | llm-agent RAG API로 오류/조치 사례 검색·등록 |
| Config Diff MCP | `config_diff_mcp` | 리발소 MwDiffDataApi로 WAS(`domain.xml`)/WEB(`http.m`) 설정 변경 이력 조회 |

공통 의존성 흐름:

```
server.py → client.py → config.py
   (MCP)      (HTTP)     (ENV)
```

- `server.py`는 `client.py`에 의존 (API 호출 위임)
- `client.py`는 `config.py`에 의존 (설정값 주입)
- 의존성 역전: 각 `*Client`는 구체적인 환경변수 접근 없이 `Settings` 객체를 주입받음

---

## 1. Email MCP (`email_mcp`)

### 모듈 구조

```
src/email_mcp/
├── __init__.py      # 패키지 docstring
├── config.py        # 환경변수 기반 설정 관리 (Settings)
├── client.py        # EmailApi HTTP 클라이언트 (EmailClient)
└── server.py        # MCP 서버 생성 및 도구 등록, 엔트리포인트 (main)
```

### 모듈 설명

#### config.py — 설정 관리
- `Settings` 클래스: `.env` 파일에서 환경변수를 로드
- 필수 환경변수: `API_BASE_URL`, `API_BEARER_TOKEN`
- 선택 환경변수: `API_SSL_VERIFY` (기본값 `false`)
- API 엔드포인트 경로는 상수로 관리

#### client.py — EmailApi 클라이언트
- `EmailClient` 클래스: `Settings`를 주입받아 httpx로 API 통신
- `send_html()`: HTML 이메일 발송 (`POST /api/v1/email/send`)
- `send_markdown()`: Markdown 이메일 발송 (`POST /api/v1/email/send_markdown`)
- 인증: Bearer Token (JWT)

#### server.py — MCP 서버
- `create_server()`: FastMCP 인스턴스 생성 및 도구 등록
- `create_email_client()`: Settings → EmailClient 팩토리
- `main()`: stdio 전송 방식으로 서버 실행

### MCP 도구

| 도구명 | 설명 | 파라미터 |
|--------|------|----------|
| `send_html_email` | HTML 이메일 발송 | `receivers`, `subject`, `content`, `sender_name`(선택) |
| `send_markdown_email` | Markdown 이메일 발송 | `receivers`, `subject`, `content`, `sender_name`(선택) |

---

## 2. Extract Error Log MCP (`extract_error_log_mcp`)

### 모듈 구조

```
src/extract_error_log_mcp/
├── __init__.py
├── config.py        # Settings, 엔드포인트 경로 상수
├── client.py         # ExtractLogClient — httpx 기반 GET/POST
└── server.py         # request_extract_log / get_extracted_log 도구 등록, main
```

### 모듈 설명

#### config.py — 설정 관리
- `email_mcp`와 동일한 `.env`(`API_BASE_URL`, `API_BEARER_TOKEN`, `API_SSL_VERIFY`)를 공유
- 엔드포인트 경로 상수: `EXTRACT_LOG_PATH`, `MDCONTENT_LIST_PATH`, `MDCONTENT_GET_PATH`

#### client.py — ExtractLogClient
- `request_extract_log()`: 로그 추출 요청 (`POST /api/v1/command_master/extract_log`)
- `get_mdcontent_list()`: `search_tags`(command_id)로 목록 조회 (`GET /api/v1/knowledge/mdcontent/list`)
- `get_mdcontent()`: `content_id`로 상세 조회 (`GET /api/v1/knowledge/mdcontent/{content_id}`)

#### server.py — MCP 서버
- `request_extract_log`: 입력 포맷 검증(날짜/시간/인스턴스ID) 후 추출 요청, `command_id` 반환
- `get_extracted_log`: `command_id` → 목록 조회로 `content_id` 획득 → 상세 조회(2단계 연속 호출)

### MCP 도구

| 도구명 | 설명 | 파라미터 |
|--------|------|----------|
| `request_extract_log` | 로그 추출 요청 | `date`, `host_id`, `time_from`, `time_to`, `was_instance_id` |
| `get_extracted_log` | 추출된 로그 조회 | `command_id` |

상세 설계 근거는 [extract_error_log_mcp 설계서](extract_error_log_mcp_design.md) 참조.

---

## 3. Error RAG MCP (`error_rag_mcp`)

오류/장애 탐지 → 로그 요약 → **과거 유사 사례 검색** → 조치 → **조치 결과 등록**이라는 전체 흐름
중, 검색과 등록 두 단계를 담당한다. llm-agent(Docker)의 RAG REST API(`/api/rag/search`,
`/api/rag/knowledge`)와 통신하며, `email_mcp`/`extract_error_log_mcp`와는 별도의 환경변수
(`RAG_*`)를 사용한다.

### 모듈 구조

```
src/error_rag_mcp/
├── __init__.py
├── config.py        # Settings, 도메인 상수 (MAX_ERROR_SUMMARY_LENGTH, MAX_ERROR_KEYWORD_COUNT,
│                     #   CONTENT_COMPOSE_TEMPLATE, REPORT_TEMPLATE 등)
├── client.py        # RagClient — search() / register() (httpx 기반)
└── server.py         # search_similar_error / register_error_resolution 도구 등록, main
                       # + content 결합·보고서 템플릿·중복제거(dedupe) 로직
```

### 모듈 설명

#### config.py — 설정 관리
- 필수 환경변수: `RAG_API_BASE_URL`, `RAG_COLLECTION_NAME`, `RAG_DOMAIN_ID`(정수로 파싱)
- 선택 환경변수: `RAG_API_BEARER_TOKEN`(없으면 인증 헤더 생략), `RAG_API_SSL_VERIFY`,
  `RAG_API_TIMEOUT`, `RAG_VECTOR_SEARCH_LIMIT`(기본 3), `RAG_TEXT_MATCHING_LIMIT`(기본 2),
  `RAG_SOURCE`(기본 `error-resolution-report`)
- 도메인 상수(환경변수가 아닌 `config.py` 상수로 관리): `MAX_ERROR_SUMMARY_LENGTH=300`,
  `MAX_ERROR_KEYWORD_COUNT=3`, `CONTENT_COMPOSE_TEMPLATE`, `LOCATION_COMPOSE_TEMPLATE`(오류
  발생 위치 = `host_id` + `was_instance_id` 결합), `REPORT_TEMPLATE`(오류 및 조치 보고서
  표준 양식)

#### client.py — RagClient
- 검색/등록 각각 단일 HTTP 호출만 책임진다(SRP). 여러 번 호출하거나 결과를 조합하는 로직은
  `server.py`에 둔다.
- `search(query, search_method, limit)`: `POST /api/rag/search` — `search_method`가
  `"vector"`(임베딩 유사도) 또는 `"text_matching"`(Qdrant `MatchText`, **`content` 필드만
  검색** — `extended_content`는 검색 대상 아님)
- `register(content, extended_content)`: `POST /api/rag/knowledge` — `source`는 `Settings`
  고정값 사용, `point_id`는 채우지 않음(항상 신규 등록)
- `collection_id`(검색)/`collection_name`(등록) 필드명 차이는 `RagClient` 내부에서 흡수

#### server.py — MCP 서버
- `search_similar_error`: `error_summary`로 벡터 검색(limit 3) + `error_keyword`로 텍스트
  매칭 검색(limit 2)을 병행 호출 → `_dedupe_by_id()`로 `id` 기준 중복 제거(동일 id는 벡터
  검색 결과를 우선)해 병합 반환
- `register_error_resolution`: `error_summary`(300자 이내) 검증 → `error_keyword`(1~3개)
  검증 → `_compose_content()`로 `content` 생성(요약+키워드 결합, text_matching이 키워드를
  찾을 수 있도록 서버가 강제 결합) → `_compose_location()`으로 `host_id`+`was_instance_id`를
  결합해 오류 발생 위치 생성 → `_compose_report()`로 `extended_content`(표준 보고서) 생성 →
  등록

### MCP 도구

| 도구명 | 설명 | 파라미터 |
|--------|------|----------|
| `search_similar_error` | 오류 요약(벡터)+키워드(텍스트 매칭) 병행 검색, id 기준 distinct 병합 | `error_summary`, `error_keyword` |
| `register_error_resolution` | 오류 및 조치 결과를 표준 보고서로 등록 | `error_summary`, `error_keyword`(최대 3개), `error_occurred_at`, `host_id`, `was_instance_id`, `error_content`, `action_taken_at`, `actor`, `action_content` |

### 의존성 흐름 및 설계 근거

```
server.py → client.py → config.py
(search_similar_error,     (RagClient:      (Settings,
 register_error_resolution:  단일 HTTP 호출만  도메인 상수)
 병합/조합/검증 로직)         책임)
```

- **SRP**: `RagClient`는 검색/등록 각 1회 HTTP 호출만 책임지고, 2회 호출·중복 제거·content
  조합·보고서 템플릿 적용 같은 도구별 특화 로직은 `server.py`에 둔다.
- **의존성 역전**: `RagClient`는 `Settings` 객체를 주입받아 동작하며 환경변수를 직접 읽지 않는다.
- **하드코딩 금지**: API 경로, 검색 결과 개수 기본값, 300자 제한, 키워드 최대 개수, content
  결합 템플릿, 보고서 양식 모두 `config.py` 상수/환경변수로 관리한다.
- 상세 요구사항과 llm-agent 실제 API 검증 결과는 [error_rag_mcp 요구사항 정의서](error_rag_mcp_requirements.md) 참조.

---

## 4. Config Diff MCP (`config_diff_mcp`)

미들웨어 설정 파일의 **변경 이력(configuration diff)** 을 조회한다. 장애 분석 시 "언제 무엇이
바뀌었는가"가 1차 원인 후보이므로 `extract_error_log_mcp`/`error_rag_mcp`와 함께 쓰이는 것을
전제로 한다. 리발소 서비스의 `MwDiffDataApi`(`/diff_data/{was|web}/list`,
`/diff_data/{was|web}/{id}`)와 통신하며, 접속 설정은 `email_mcp`/`extract_error_log_mcp`와
동일한 `API_*` 환경변수를 공유한다.

### 모듈 구조

```
src/config_diff_mcp/
├── __init__.py
├── config.py        # Settings, ResourceSpec(WAS_RESOURCE/WEB_RESOURCE), 경로·형식·메시지 상수
├── client.py        # DiffClient — list_diffs() / get_diff_detail() (httpx 기반)
└── server.py        # get_diff_was / get_diff_web 도구 등록, main
                     # + 날짜 정규화·건수 분기·최신순 정렬·old 제거·응답 조립 로직
```

### 모듈 설명

#### config.py — 설정 관리
- 필수 환경변수: `API_BASE_URL`, `API_BEARER_TOKEN` (다른 두 리발소 연동 서버와 공유)
- 선택 환경변수: `API_SSL_VERIFY`, `API_TIMEOUT`, `DIFF_DATE_PADDING_DAYS`(기본 1)
- `ResourceSpec`(frozen dataclass): 조회 대상 한 종류의 정의를 묶는다 — `list_path`,
  `detail_path`, `filter_key`(`domain_id`/`host_id`), `config_file_name`(`domain.xml`/`http.m`),
  `missing_filter_message`. `WAS_RESOURCE`/`WEB_RESOURCE` 두 인스턴스를 제공한다.
- 도메인 상수: `DATE_FORMAT`, `CREATE_ON_FORMATS`, `DEFAULT_DATE_PADDING_DAYS`,
  `EXCLUDED_DETAIL_FIELDS=("old",)`, `NOT_FOUND_MESSAGE`, `MULTIPLE_RESULT_NOTICE_TEMPLATE`,
  `MISSING_HOST_ID_MESSAGE`, `MISSING_DOMAIN_ID_MESSAGE`

#### client.py — DiffClient
- 목록/상세 각각 단일 HTTP GET만 책임진다(SRP). 응답을 가공하지 않는다.
- `list_diffs(resource, params)`: `GET /diff_data/{was|web}/list` — 실제 응답은 `{"data": [...]}`
  봉투 형태이며(OpenAPI 스펙은 배열로 선언), 봉투 해제는 `server.py`의 `_extract_records()`가
  담당한다(두 형태 모두 허용).
- `get_diff_detail(resource, record_id)`: `GET /diff_data/{was|web}/{id}`
- 두 메서드 모두 `ResourceSpec`을 받으므로 대상이 늘어나도 클라이언트 코드는 그대로다.

#### server.py — MCP 서버
- `_get_diff()` 하나가 WAS/WEB 공통 흐름을 담당하고, 두 도구는 `ResourceSpec`과 필터값만
  달리해 위임한다.
- **식별자 검증**: `host_id`/`domain_id`가 없거나 공백이면 API를 호출하지 않고
  `missing_filter_message`를 반환해 AI Agent가 사용자에게 되묻도록 유도한다.
- **날짜 정규화**(`_normalize_date_range`): 둘 다 없으면 날짜 파라미터 미전송(API가 최근 1건
  반환) / 한쪽만 있거나 두 값이 같으면 앞뒤 `date_padding_days` 확장 / 서로 다른 구간은 그대로.
- **건수 분기**: 0건 → `존재하지 않습니다.` / 1건 → 상세 반환 / 2건 이상 → 최신 1건 + `notice`
- **최신순 정렬**(`_sort_by_recency`): 목록 API의 정렬 순서를 신뢰하지 않고 `create_on` 내림차순
  정렬. 파싱 실패 시 문자열 비교 → `id` 내림차순으로 대체한다.
- **`old` 제거**(`_strip_excluded_fields`): 이전 설정 전문은 `new`+`unified_diff`로 복원 가능한
  파생 정보이므로 AI Agent 토큰 절약을 위해 반환하지 않는다.
- 모든 실패(식별자 누락, 날짜 형식 오류, 상세 404, HTTP 오류)는 예외를 던지지 않고
  `{found, total_count, message}` 구조로 변환한다.

### MCP 도구

| 도구명 | 설명 | 파라미터 |
|--------|------|----------|
| `get_diff_web` | WEB 설정(`http.m`) 변경 내역 조회 | `host_id`(필수), `start_date`, `end_date` |
| `get_diff_was` | WAS 설정(`domain.xml`) 변경 내역 조회 | `domain_id`(필수), `start_date`, `end_date` |

응답은 항상 동일한 JSON 구조다: `{"found", "total_count", "notice", "diff"}` 또는
`{"found": false, "total_count": 0, "message"}`.

### 의존성 흐름 및 설계 근거

```
server.py      →   client.py    →   config.py
(get_diff_was,     (DiffClient:     (Settings,
 get_diff_web:      단일 HTTP GET만   ResourceSpec,
 정규화/분기/정렬/    책임, 가공 없음)   경로·메시지 상수)
 응답 조립)
```

- **SRP**: `DiffClient`는 HTTP 호출만, 날짜 정규화·정렬·필드 제외·응답 조립은 `server.py`.
- **OCP**: 조회 대상이 추가되면 `ResourceSpec` 인스턴스와 얇은 도구 래퍼만 추가하면 되고
  공통 흐름 코드(`_get_diff`)는 수정하지 않는다.
- **의존성 역전**: `DiffClient`는 `Settings`를 주입받아 동작하며 환경변수를 직접 읽지 않는다.
- **하드코딩 금지**: API 경로, 필터 키, 설정 파일명, 날짜 형식, 여유일수, 제외 필드, 안내 문구를
  모두 `config.py` 상수/환경변수로 관리하고 도구 설명도 이 상수로 조립한다.
- 상세 요구사항은 [config_diff_mcp 요구사항 정의서](config_diff_mcp_requirements.md) 참조.
