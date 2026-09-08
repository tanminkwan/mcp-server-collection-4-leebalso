# 사용 가이드 (요약)

> 오프라인 환경 설치를 포함한 상세 가이드는 [installation-guide.md](installation-guide.md)를 참조한다.
> 서버별 상세 설계는 [architecture.md](architecture.md), [extract_error_log_mcp 설계서](extract_error_log_mcp_design.md),
> [error_rag_mcp 요구사항 정의서](error_rag_mcp_requirements.md),
> [config_diff_mcp 요구사항 정의서](config_diff_mcp_requirements.md)를 참조한다.

## 빠른 시작 (인터넷 가능한 환경)

```bash
# 1. 가상환경 생성 및 활성화
python3.11 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

# 2. 의존성 설치
pip install -e ".[dev]"

# 3. 환경변수 설정
cp .env.example .env
# .env 파일을 편집하여 실제 값 입력

# 4. 실행 (stdio) — 필요한 서버만 실행
email-mcp
extract-error-log-mcp
error-rag-mcp
config-diff-mcp
```

## 환경변수

### Email MCP / Extract Error Log MCP / Config Diff MCP (공유)

| 변수 | 설명 | 필수 | 기본값 |
|------|------|:----:|--------|
| `API_BASE_URL` | EmailApi/로그 추출/변경 이력 API 서버 주소 | O | — |
| `API_BEARER_TOKEN` | JWT 인증 토큰 | O | — |
| `API_SSL_VERIFY` | SSL 인증서 검증 여부 | X | `false` |
| `API_TIMEOUT` | HTTP 요청 타임아웃(초) | X | `60` |
| `EMAIL_RECIPIENT_MAPPING` | 수신자 이름-이메일 매핑 (JSON 또는 `이름:이메일` 콤마 구분, Email MCP 전용) | X | — |
| `DIFF_DATE_PADDING_DAYS` | 단일 일자 지정 시 앞뒤로 확장할 일수 (Config Diff MCP 전용) | X | `1` |

> **수신자 이름 매핑**: `EMAIL_RECIPIENT_MAPPING` 환경변수에 이름과 이메일을 등록해두면, `receivers`에 이메일 대신 이름을 입력해도 서버가 이메일 주소로 자동 변환합니다. (예: `EMAIL_RECIPIENT_MAPPING=홍길동:hong@example.com`)

### Error RAG MCP (`error_rag_mcp`, 별도 환경변수)

| 변수 | 설명 | 필수 | 기본값 |
|------|------|:----:|--------|
| `RAG_API_BASE_URL` | llm-agent 서비스 기본 URL | O | — |
| `RAG_API_BEARER_TOKEN` | 인증 토큰 (현재 미인증 접근 가능) | X | — (헤더 생략) |
| `RAG_API_SSL_VERIFY` | SSL 인증서 검증 여부 | X | `false` |
| `RAG_API_TIMEOUT` | HTTP 요청 타임아웃(초) | X | `60` |
| `RAG_COLLECTION_NAME` | 고정 콜렉션 식별자 | O | — |
| `RAG_DOMAIN_ID` | 고정 도메인 ID (정수) | O | — |
| `RAG_VECTOR_SEARCH_LIMIT` | 벡터 검색 결과 개수 | X | `3` |
| `RAG_TEXT_MATCHING_LIMIT` | 텍스트 매칭 검색 결과 개수 | X | `2` |
| `RAG_SOURCE` | 등록 시 지식의 `source` 태그 | X | `error-resolution-report` |

## MCP 도구

### Email MCP

| 도구명 | 설명 | 파라미터 |
|--------|------|----------|
| `send_html_email` | HTML 이메일 발송 | `receivers` (이름 또는 이메일), `subject`, `content`, `sender_name`(선택) |
| `send_markdown_email` | Markdown 이메일 발송 | `receivers` (이름 또는 이메일), `subject`, `content`, `sender_name`(선택) |

### Extract Error Log MCP

| 도구명 | 설명 | 파라미터 |
|--------|------|----------|
| `request_extract_log` | 서버 에러 로그 추출 요청 (command_id 반환) | `date`, `host_id`, `time_from`, `time_to`, `was_instance_id` |
| `get_extracted_log` | command_id로 추출된 로그(마크다운) 조회 | `command_id` |

### Error RAG MCP

| 도구명 | 설명 | 파라미터 |
|--------|------|----------|
| `search_similar_error` | 오류 요약(벡터 검색)+키워드(텍스트 매칭)로 과거 유사 오류/조치 사례 검색, id 기준 distinct 병합 | `error_summary`, `error_keyword` |
| `register_error_resolution` | 오류 및 조치 결과를 표준 보고서 형식으로 등록 | `error_summary`, `error_keyword`(최대 3개), `error_occurred_at`, `host_id`, `was_instance_id`, `error_content`, `action_taken_at`, `actor`, `action_content` |

> `search_similar_error`는 오류 발생 시 과거 유사 사례·조치 방법을 먼저 확인하는 용도이고,
> `register_error_resolution`은 조치가 끝난 뒤 그 결과를 다시 지식으로 쌓는 용도이다. `content`
> (검색 대상)는 `error_summary`+`error_keyword`를 서버가 결합해 생성하며, `extended_content`
> (보고서 본문)는 검색되지 않으므로 키워드를 반드시 `content`에도 포함시켜야 한다 — 자세한 근거는
> [요구사항 정의서](error_rag_mcp_requirements.md) 참조.

### Config Diff MCP

| 도구명 | 설명 | 파라미터 |
|--------|------|----------|
| `get_diff_web` | WEB 설정(`http.m`) 변경 내역 조회 | `host_id`(필수), `start_date`(선택), `end_date`(선택) |
| `get_diff_was` | WAS 설정(`domain.xml`) 변경 내역 조회 | `domain_id`(필수), `start_date`(선택), `end_date`(선택) |

> - 사용자는 `WAS`/`WEB` 대신 설정 파일명(`domain.xml` / `http.m`)으로 지칭하기도 하며, 두 표현
>   모두 같은 도구로 라우팅된다.
> - 날짜를 지정하지 않으면 **가장 최근 변경 1건**을 반환한다("최근 변경 내역" 요청).
>   하루만 지목하면(`start_date`만, 또는 `start_date == end_date`) 앞뒤로 `DIFF_DATE_PADDING_DAYS`
>   만큼 여유를 두고 조회한다. 서로 다른 두 날짜를 주면 그 구간을 그대로 사용한다.
> - `host_id`/`domain_id`는 **필수**다. 없으면 API를 호출하지 않고 사용자에게 되묻도록 유도하는
>   메시지를 반환한다. **WAS는 서버명(`host_id`)으로 조회할 수 없다** — `domain_id`가 필요하다.
> - 응답에는 이전 설정 전문(`old`)이 포함되지 않는다(토큰 절약). 필요하면 `new`와 `unified_diff`로
>   복원한다. 2건 이상이면 최신 1건만 반환하고 `notice`에 전체 건수를 안내한다.
> - 자세한 근거는 [요구사항 정의서](config_diff_mcp_requirements.md) 참조.

## 테스트

```bash
pytest
```

서버별로 독립된 `tests/` 하위 테스트를 가지며, 커버리지 리포트 포함(최소 85% 이상 유지).
