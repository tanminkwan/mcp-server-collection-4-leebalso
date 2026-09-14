# Read Server File MCP 요구사항 정의서 겸 설계서 (`read_server_file_mcp`)

> 상태: **구현 완료 · 실서버 검증 완료** (2026-09-14).
> 대상 API 스펙은 실제 서버(`https://app.mwm.local:20443`)의 OpenAPI 문서
> (`GET /api/v1/_openapi`)에서 `CommandMasterApi` 태그 정의를 직접 조회해 확보했고,
> `host_id → agent_id` 조회 경로와 `parameters → additional_params` 저장 형태는
> 실서버에 실제 요청을 보내 확인했다 (10절 참조).
>
> **구현 완료** (2026-09-14): `src/read_server_file_mcp/`(`config.py`/`client.py`/`server.py`) 및
> `tests/read_server_file_mcp/`(`test_config.py`/`test_client.py`/`test_server.py`)를 본 문서의
> 3~9절대로 TDD로 구현했다(테스트 선작성 → red 확인 → 구현). `pytest` 전체 206개(신규 86개 포함)
> 모두 통과, `read_server_file_mcp` 라인 커버리지 99%(`config.py`/`client.py` 100%,
> `server.py`는 `if __name__ == "__main__"` 1줄만 미커버). 전체 커버리지 98%로 요구사항 85% 충족.
> `pyproject.toml`에 `read-server-file-mcp` 엔트리포인트와 커버리지 대상을 추가했고,
> `.env.example`에 `READ_SERVER_FILE_RESULT_WAIT_SECONDS`를 추가했다.
>
> **실서버 검증 완료** (2026-09-14): 실제 리발소 서버를 대상으로 다음을 end-to-end 확인했다.
> - 도구 스키마상 `host_id`/`file_path`/`command_id`가 `required`로 노출됨 (`list_tools()` 확인).
> - `host_id` 누락 되묻기, 상대 경로 거부, 미등록 host_id 처리가 **API 호출 없이** 동작.
> - `host_id=hennry-PN40` → `agent_id=hennry-PN40_hennry_J` 조회 후 명령 생성 성공
>   (`command_id=0b2669107f69`), `additional_params`에 경로 문자열이 그대로 저장됨.
> - 결과 미도착 시 `found: false` + 재시도 안내 반환.
> - 실제 결과가 채워진 명령(`command_id=5d3dade3b6a1`)으로 조회해 **응답 필드 매핑이 실제 응답과
>   일치**함을 확인했고, `result_text`가 `"NO CHANGE"`인 경우 `agent_error_sentinel`이 정상
>   탐지되는 것도 확인했다.
>
> ⚠️ 남은 미검증 항목: **정상 파일 내용이 채워진 `result_text`** 는 실서버에서 재현하지 못했다.
> 검증 환경의 에이전트가 주기 명령(`Read.domain.xml`)만 수행하고 ad-hoc `COMMON.READFILE`
> 명령을 가져가지 않았기 때문이다(에이전트 측 환경 이슈이며 본 MCP 서버 코드와 무관하다).
> 해당 경로는 실제 응답 스키마에 기반한 단위 테스트로 커버되어 있다.
>
> 기존 `email_mcp`, `extract_error_log_mcp`, `error_rag_mcp`, `config_diff_mcp`와 동일한
> 스타일(아키텍처, 의존성, 환경설정 패턴)로 구성된 독립적인 5번째 MCP 서버로 추가한다.

---

## 1. 개요

### 1.1 목적
AI Agent가 **서버(호스트)의 특정 위치에 있는 파일 내용을 자연어로 읽을 수 있도록** 하는 MCP
서버이다. 리발소의 에이전트(agent)에게 "파일을 읽어라"는 명령을 하달하고(`command_id` 획득),
잠시 후 그 실행 결과(파일 내용)를 조회한다.

- `request_read_server_file` — 파일 읽기 명령을 주문하고 `command_id`를 반환한다.
- `get_read_server_file_result` — `command_id`로 실행 결과(`additional_params`, `result_text`)를 조회한다.

명령 하달과 결과 조회가 **비동기로 분리**된 2단계 구조인 이유는, 실제 파일 읽기를 수행하는 주체가
서버가 아니라 대상 호스트에 설치된 에이전트이기 때문이다. 에이전트는 주기적으로 서버를 폴링해
명령을 가져가 실행하고 결과를 되돌려준다. 따라서 명령 생성 직후에는 결과가 존재하지 않는다.

이는 `extract_error_log_mcp`(`request_extract_log` → 대기 → `get_extracted_log`)와 동일한
2단계 패턴이며, 도구 사용법도 의도적으로 같은 형태로 맞춘다.

### 1.2 배경 시나리오 (AI Agent 관점)
1. 사용자가 "pcbkaa11 서버의 /var/log/messages 좀 보여줘"와 같이 요청한다.
2. **[본 서버] `request_read_server_file`** 로 해당 호스트에 파일 읽기 명령을 하달하고 `command_id`를 받는다.
3. AI Agent는 사용자에게 "파일 읽기에 약 30초 정도 소요됩니다"라고 먼저 안내한 뒤 실제로 대기한다.
4. **[본 서버] `get_read_server_file_result`** 로 결과를 조회한다. 아직 결과가 없으면 재시도한다.
5. `result_text`가 **파일 내용인지 오류 메시지인지 AI Agent가 판단**해 사용자에게 응답한다 (6.3절).

### 1.3 "서버" 용어
사용자는 대상 호스트를 **`서버`, `호스트`, `시스템`, `host`, `host id`** 등 여러 표현으로 지칭한다.
모두 `host_id` 파라미터를 가리키는 같은 개념으로 처리한다 (`extract_error_log_mcp`의
`request_extract_log`가 `host_id`를 "'서버' 또는 '시스템'이라고도 부름"으로 설명하는 것과 동일).

### 1.4 연동 대상 API
`리발소(VER:20260811.001)` 서비스의 REST API 3종을 사용한다.

| # | Method | Path | 태그 | 용도 |
|---|--------|------|------|------|
| 1 | GET | `/api/v1/model/column_all/ag_agent.agent_id` | `ModelSpecView` | `host_id` → `agent_id` **조회** |
| 2 | POST | `/api/v1/command_master/create` | `CommandMasterApi` | 파일 읽기 **명령 생성** (`command_id` 획득) |
| 3 | GET | `/api/v1/command_master/result` | `CommandMasterApi` | 명령 **실행 결과 조회** |

---

## 2. 기능 요구사항 요약

| 구분 | MCP 도구명 | 대상 API | 설명 |
|------|-----------|----------|------|
| 명령 주문 | `request_read_server_file` | 1 → 2 | `host_id`로 `agent_id`를 찾아 파일 읽기 명령을 생성하고 `command_id` 반환 |
| 결과 확인 | `get_read_server_file_result` | 3 | `command_id`로 `additional_params`(파일 위치)와 `result_text`(파일 내용) 확인 |

---

## 3. 기능 및 도구(Tools) 설계

### 3.1 `request_read_server_file`

**입력**

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `host_id` | ✅ | 대상 서버 ID. 사용자가 '서버'/'호스트'/'시스템'이라고 부르는 값 |
| `file_path` | ✅ | 읽을 파일의 **절대 경로** (예: `/var/log/messages`, `C:\logs\app.log`) |

**처리 흐름**

1. `host_id` 검증 — 비어 있으면 호출하지 않고 **사용자에게 되묻도록** 유도하는 메시지 반환 (3.3절).
2. `file_path` 검증 — 비어 있으면 되묻기 유도. 절대 경로가 아니거나 `..`를 포함하면 거부 (5.4절).
3. `host_id` → `agent_id` 조회 (5.1절). 0건이면 "등록된 에이전트가 없다"는 메시지 반환.
4. 파일 읽기 명령 생성 (5.2절) → `command_id` 획득.
5. `command_id` / `agent_id` / `file_path`를 담은 응답 반환 (6.1절).

**출력**: 6.1절 참조.

### 3.2 `get_read_server_file_result`

**입력**

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `command_id` | ✅ | `request_read_server_file` 호출 결과로 받은 명령 ID |

**처리 흐름**

1. `command_id` 검증 — 비어 있으면 되묻기 유도 메시지 반환.
2. 결과 조회 (5.3절).
3. `data`가 `null`이면 **아직 에이전트가 결과를 반환하지 않은 것**으로 보고 재시도 안내 반환 (6.2절).
4. `additional_params`(파일 위치)와 `result_text`(파일 내용 또는 오류 메시지)를 반환 (6.3절).

**출력**: 6.2, 6.3절 참조.

### 3.3 필수 식별자 누락 시 되묻기 (필수)

`config_diff_mcp`의 `host_id`/`domain_id` 정책과 동일하게 처리한다. AI Agent가 값을 **추측하거나
빈 값으로 호출하지 않도록**, 값이 비어 있으면 API를 호출하지 않고 되묻기를 유도하는 메시지를 반환한다.

| 누락 항목 | 반환 메시지 |
|-----------|-------------|
| `host_id` | 어느 서버(호스트)의 파일인지 사용자에게 확인하도록 안내 |
| `file_path` | 어느 위치의 어떤 파일인지 **절대 경로**로 확인하도록 안내 |
| `command_id` | 먼저 `request_read_server_file`을 호출해 `command_id`를 받도록 안내 |

### 3.4 2단계 호출 사이의 대기 (필수)

`request_read_server_file` 호출 후 곧바로 `get_read_server_file_result`를 호출하면 대부분 결과가 없다.
AI Agent는 다음을 지켜야 하며, 이 규칙을 서버 instructions와 도구 설명에 명시한다.

1. `request_read_server_file`로 `command_id`를 받는다.
2. 사용자에게 **"파일 읽기에 약 30초 정도 소요됩니다"** 라고 먼저 안내한다.
3. 실제로 약 30초 대기한다.
4. `get_read_server_file_result`를 호출한다.
5. 결과가 없으면(`found: false`) 추가로 대기한 뒤 재시도한다.

대기 시간 기본값은 하드코딩하지 않고 config 상수(`DEFAULT_RESULT_WAIT_SECONDS`)로 관리하며,
환경변수 `READ_SERVER_FILE_RESULT_WAIT_SECONDS`로 재정의할 수 있다. 이 값은 도구 설명 문자열에
주입되어 AI Agent에게 전달된다.

---

## 4. `host_id → agent_id` 조회 방식

### 4.1 배경
`POST /api/v1/command_master/create`는 대상을 **`target_agent_id`(에이전트 ID)** 로만 지정할 수
있고 `host_id`를 받지 않는다. 반면 사용자는 항상 서버(호스트)를 기준으로 말한다. 따라서 호출 전에
`host_id`를 `agent_id`로 변환해야 한다.

에이전트 정보는 `ag_agent` 테이블에 있으며, 이 테이블은 `agent_id`와 `host_id`를 모두 보유한다.
리발소는 임의의 테이블·컬럼을 조건부로 조회할 수 있는 범용 API(`ModelSpecView`)를 제공하므로
이를 사용한다.

> `GET /api/v1/mw_server/list`도 확인했으나 응답에 `agent_id`가 없어(호스트 마스터 정보만 보유)
> 이 목적에는 사용할 수 없다.

### 4.2 조회 요청

```
GET /api/v1/model/column_all/ag_agent.agent_id
    ?condition={"column":"host_id","operator":"eql","value":"<host_id>"}
```

- 경로의 `{table_column}`은 `<테이블>.<컬럼>` 형식이다 → `ag_agent.agent_id`.
- `condition`은 **JSON 문자열**이며 `column`/`operator`/`value` 3개 키를 가진다.
  `operator`는 완전 일치를 뜻하는 `eql`을 사용한다.

### 4.3 조회 응답

```json
{"list": [{"pk": 1, "value": "hennry-PN40_hennry_J"}]}
```

- `list[].value`가 `agent_id`, `pk`는 `ag_agent.id`이다.
- **0건**: 해당 호스트에 등록된 에이전트가 없음 → 명령을 생성하지 않고 오류 응답 (6.4절).
- **1건**: 정상. 그 `agent_id`를 사용한다.
- **2건 이상**: 한 호스트에 여러 에이전트가 등록된 경우다. **첫 번째 `agent_id`를 사용**하고,
  응답의 `notice`에 전체 목록을 함께 안내해 AI Agent가 다른 에이전트로 재시도할 수 있게 한다.

---

## 5. API 연동 설계

### 5.1 에이전트 조회 — `GET /api/v1/model/column_all/{table_column}`
4절 참조. 테이블명(`ag_agent`), 컬럼명(`agent_id`), 필터 컬럼(`host_id`), 연산자(`eql`),
응답 키(`list`/`value`)는 모두 config 상수로 관리한다 (하드코딩 금지).

### 5.2 명령 생성 — `POST /api/v1/command_master/create`

**요청 본문**

```json
{
  "command_type_id": "COMMON.READFILE",
  "target_agent_id": ["hennry-PN40_hennry_J"],
  "parameters": "/var/log/messages"
}
```

| 필드 | 값 | 비고 |
|------|----|------|
| `command_type_id` | `COMMON.READFILE` | 절대 경로 파일 읽기 명령 타입 (5.2.1절) |
| `target_agent_id` | `[agent_id]` | 스펙상 배열. 단일 문자열도 허용되나 **배열로 보낸다** |
| `parameters` | 파일 절대 경로 **문자열** | 객체가 아닌 **문자열**로 보내야 한다 (5.2.2절) |

**응답 (201)**

```json
{"command_id": "61022517ccc1", "message": "OK", "return_code": 1}
```

#### 5.2.1 `COMMON.READFILE` 선택 근거
실서버의 `ag_command_type`에 등록된 명령 타입은 다음과 같다.

```
updateToken, sslcertifile.download, test.download, mwagent.download,
Read.domain.xml, SYNC.ROLE_PERMISSIONS, WAS.REBUILD, CALL.GET_SSL_CERTI,
EXTRACT.LOG, COMMON.READFILE
```

이 중 `Read.domain.xml`처럼 대상 파일이 고정된 타입과 달리, `COMMON.READFILE`은
`target_file_path`/`target_file_name`이 **빈 값**으로 등록되어 있어 **파일 위치를 호출 시점에
지정**할 수 있다. 에이전트 측 처리 클래스는 `ReadFullPathFile`
(`command_class = ReadFullPathFile`, '파일 Read(파일 이름 후 지정)')이며, 그 구현은
`additional_params`를 **읽을 파일의 절대 경로 문자열 그 자체**로 해석한다.

#### 5.2.2 `parameters` → `additional_params` 저장 형태 (실측)
`create`의 `parameters`는 스펙상 "JSON 객체 또는 문자열"이다. 에이전트의 `ReadFullPathFile`은
`additional_params`를 **경로 문자열**로 읽으므로, `parameters`에는 객체가 아니라 **경로 문자열을
그대로** 보내야 한다. 실서버 검증 결과 문자열로 보낸 값이 `ag_command_detail.additional_params`에
그대로 저장되는 것을 확인했다 (10절 #1).

### 5.3 결과 조회 — `GET /api/v1/command_master/result`

```
GET /api/v1/command_master/result?command_id=<command_id>
```

- 스펙상 `command_id` / `agent_id` / `host_id` 중 **하나 이상**이 필요하다.
  본 서버는 요청한 명령의 결과를 정확히 특정하기 위해 **`command_id`만** 사용한다.
- 조건에 맞는 결과가 여러 건이면 서버가 `create_on` 기준 **가장 최근 1건**만 반환한다.

**응답 (200) — 결과 있음**

```json
{
  "data": {
    "command_id": "61022517ccc1",
    "agent_id": "hennry-PN40_hennry_J",
    "host_id": "hennry-PN40",
    "command_type_id": "COMMON.READFILE",
    "command_class": "ReadFullPathFile",
    "additional_params": "/var/log/messages",
    "result_text": "<파일 내용 또는 오류 메시지>",
    "result_status": "...",
    "result_message": "...",
    "complited_date": "2026-09-14 14:52:03",
    "create_on": "2026-09-14 14:51:58"
  },
  "message": "OK",
  "return_code": 1
}
```

**응답 (200) — 결과 없음 (아직 에이전트가 수행하지 않음)**

```json
{"data": null, "message": "No result found", "return_code": 0}
```

> `data: null`은 **오류가 아니라 "아직 결과 없음"** 이다. HTTP 상태 코드는 200이다.

### 5.4 `file_path` 사전 검증
에이전트는 경로 traversal과 허용 디렉터리를 검사해, 위반 시 `Error:FileNotFoundException`을
반환한다. 왕복 대기(수십 초)를 낭비하지 않도록 **명령 생성 전에** 명백한 오류를 먼저 거른다.

| 검증 | 규칙 |
|------|------|
| 빈 값 | 거부 → 되묻기 유도 (3.3절) |
| 상대 경로 | 거부. 절대 경로만 허용 — POSIX(`/...`) 또는 Windows(`C:\...`, `C:/...`, `\\서버\공유`) |
| `..` 포함 | 거부 (path traversal) |

> 에이전트가 읽을 수 있는 디렉터리는 에이전트 측 `agent.properties`
> (`security.allowed_read_paths`)와 기본 허용 목록으로 제한된다. 이 목록은 호스트마다 다르고
> MCP 서버가 알 수 없으므로 **사전 검증하지 않는다** — 허용되지 않은 경로는 실행 결과의
> `result_text`에 오류로 나타나며 이를 AI Agent가 판단한다 (6.3절).

---

## 6. 응답 형식 설계

모든 도구는 JSON 문자열을 반환한다 (기존 4개 MCP 서버와 동일).

### 6.1 `request_read_server_file` — 성공

```json
{
  "requested": true,
  "command_id": "61022517ccc1",
  "host_id": "hennry-PN40",
  "agent_id": "hennry-PN40_hennry_J",
  "file_path": "/var/log/messages",
  "notice": "파일 읽기에 약 30초 정도 소요됩니다. ..."
}
```

호스트에 에이전트가 2개 이상이면 `notice`에 선택된 에이전트와 전체 후보를 안내한다.

### 6.2 `get_read_server_file_result` — 아직 결과 없음

```json
{
  "found": false,
  "command_id": "61022517ccc1",
  "message": "아직 실행 결과가 도착하지 않았습니다. ... 잠시 후 다시 조회하세요."
}
```

### 6.3 `get_read_server_file_result` — 결과 있음 (핵심 요구사항)

```json
{
  "found": true,
  "command_id": "61022517ccc1",
  "file_path": "/var/log/messages",
  "result_text": "...",
  "agent_error_sentinel": null,
  "host_id": "hennry-PN40",
  "agent_id": "hennry-PN40_hennry_J",
  "result_status": "COMPLITED",
  "result_message": "",
  "complited_date": "2026-09-14 14:52:03",
  "notice": "result_text는 파일 내용일 수도, 오류 메시지일 수도 있습니다. ..."
}
```

- `file_path` — 응답의 `additional_params`. **실제로 읽으라고 지시된 파일 위치**이며,
  요청한 경로와 일치하는지 확인하는 용도다.
- `result_text` — **파일 내용 또는 오류 메시지**. 가공하지 않고 원문 그대로 전달한다.

**판단 책임은 호출한 AI Agent에 있다.** 서버는 임의로 성공/실패를 단정하지 않는다.
다만 판단을 돕기 위해, 에이전트가 반환하는 **알려진 오류 문구와 정확히 일치**하는 경우에만
`agent_error_sentinel`에 그 값을 채운다 (일치하지 않으면 `null`).

| `result_text` 값 | 의미 |
|------------------|------|
| `Error:FileNotFoundException` | 파일이 없거나, 경로가 허용되지 않았거나, path traversal로 차단됨 |
| `Error:IOException` | 파일 읽기 중 입출력 오류 |
| `Error:UnsupportedEncodingException` | 인코딩 오류 |
| `Error:NoSuchAlgorithmException` | 해시 계산 오류 |
| `NO CHANGE` | 이전 결과와 내용이 동일해 본문을 생략함 (파일 내용 아님) |

> `agent_error_sentinel`은 **위 목록과 완전히 일치할 때만** 채워지는 보조 힌트다.
> 파일 내용 자체가 `FileNotFound ...` 같은 문자열을 담고 있을 수도 있으므로,
> `agent_error_sentinel`이 `null`이라고 해서 반드시 정상 파일 내용이라는 뜻은 아니다.
> 최종 판단은 AI Agent가 `result_text` 전체를 보고 내려야 한다.

### 6.4 오류

```json
{"requested": false, "message": "<사유>"}
```
```json
{"found": false, "message": "<사유>"}
```

| 상황 | 메시지 |
|------|--------|
| `host_id` 누락 | 사용자에게 대상 서버를 되묻도록 안내 |
| `file_path` 누락 | 사용자에게 파일 절대 경로를 되묻도록 안내 |
| `file_path` 형식 오류 | 절대 경로가 아님 / `..` 포함 |
| `command_id` 누락 | 먼저 `request_read_server_file`을 호출하도록 안내 |
| 에이전트 0건 | 해당 host_id로 등록된 에이전트가 없음 (host_id 오타 가능성 안내) |
| `command_id` 미수신 | 생성 응답에 `command_id`가 없음 |
| HTTP/네트워크 오류 | 예외 메시지를 담아 반환 |

---

## 7. 환경 변수

접속 정보는 기존 서버들과 **공유**한다 (`email_mcp` / `extract_error_log_mcp` /
`config_diff_mcp`와 동일).

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `API_BASE_URL` | ✅ | — | 리발소 API 베이스 URL |
| `API_BEARER_TOKEN` | ✅ | — | 장기 토큰 |
| `API_SSL_VERIFY` | ❌ | `false` | SSL 인증서 검증 여부 |
| `API_TIMEOUT` | ❌ | `60` | HTTP 타임아웃(초) |
| `READ_SERVER_FILE_RESULT_WAIT_SECONDS` | ❌ | `30` | 명령 주문 후 결과 조회까지 권장 대기 시간(초). 도구 설명에 주입된다 |

---

## 8. 프로젝트 구조

```
src/read_server_file_mcp/
├── __init__.py
├── config.py    # 상수 + Settings (환경변수 로드, URL 생성)
├── client.py    # HTTP 통신 (agent 조회 / 명령 생성 / 결과 조회)
└── server.py    # MCP 도구 2개 등록, 검증·응답 조립

tests/read_server_file_mcp/
├── __init__.py
├── test_config.py
├── test_client.py
└── test_server.py
```

### 8.1 모듈 책임 (SOLID)

| 모듈 | 단일 책임 | 비고 |
|------|-----------|------|
| `config.py` | 상수 정의 및 환경변수 로드 | 모든 리터럴이 여기 모인다 (그라운드 룰 3) |
| `client.py` | HTTP 요청/응답 | 응답을 가공하지 않고 그대로 반환 |
| `server.py` | 입력 검증, 흐름 제어, 응답 조립 | 판단·분기의 유일한 책임자 |

- **의존성 역전**: `ReadServerFileClient`는 `Settings`를 주입받고, `server`는 `ReadServerFileClient`를
  주입받는다. 테스트에서 대체 가능하다.
- **명령 타입 고정 (의도적 제약)**: 본 서버는 `COMMON.READFILE` **외의 명령을 생성할 수 없다**.
  명령 타입은 `config.py`의 `READ_FILE_COMMAND_TYPE_ID` 상수로 고정되고,
  `ReadServerFileClient.create_read_file_command(agent_id, file_path)`가 그 상수를 직접 사용하며,
  MCP 도구 시그니처(`request_read_server_file(host_id, file_path)`)에도 노출되지 않는다.
  호출하는 AI Agent가 명령 타입을 지정할 통로를 열어 두면 이 서버가 임의 명령 실행
  (`ExeShell`, `WAS.REBUILD` 등) 경로가 되므로, 범용 `create_command`를 제공하지 않는다.
  다른 명령 타입이 필요해지면 **그 용도의 전용 메서드·전용 도구를 별도로 추가**한다
  (`extract_error_log_mcp`가 `EXTRACT.LOG`를 위해 별도 서버로 존재하는 것과 같은 방식).

---

## 9. MCP 서버 메타데이터 (AI Agent 사용성)

- 서버명: `read-server-file-mcp`
- 엔트리포인트: `read-server-file-mcp = "read_server_file_mcp.server:main"`
- instructions에 다음을 명시한다.
  - "서버/호스트의 특정 파일 내용을 읽는" 서버임 (트리거 예시 포함).
  - `host_id`는 '서버'/'호스트'/'시스템'으로 불린다는 점.
  - `host_id`와 `file_path`는 **필수**이며 추측하지 말고 되물어야 한다는 점.
  - 주문 → 안내 → 대기 → 조회의 2단계 절차 (3.4절).
  - `result_text`가 파일 내용일 수도 오류 메시지일 수도 있어 **AI Agent가 판단**해야 한다는 점.

---

## 10. Open Issues / 검증 기록

### #1 (해소됨) `parameters`를 객체로 보낼 것인가 문자열로 보낼 것인가
OpenAPI 스펙의 `parameters` 예시는 객체(`{"module":"nginx","restart":true}`)지만, 에이전트의
`ReadFullPathFile`은 `additional_params`를 경로 **문자열**로 읽는다. 실서버에 문자열로 요청해
`ag_command_detail.additional_params`에 `/var/log/syslog`가 그대로 저장되는 것을 확인했다
(2026-09-14, `command_id=61022517ccc1`). → **문자열로 전송**하는 것으로 확정.

### #2 (해소됨) `host_id → agent_id` 조회 경로
`mw_server/list`에는 `agent_id`가 없어 사용할 수 없었다. `ag_agent` 테이블에 두 값이 함께 있고,
범용 조회 API로 조건 조회가 가능함을 확인했다 (4.2절). 실서버에서 `host_id=hennry-PN40` →
`agent_id=hennry-PN40_hennry_J` 조회 성공.

### #3 결과 도착까지의 소요 시간
에이전트 폴링 주기에 의존하므로 확정값이 없다. `extract_error_log_mcp`가 약 1분을 안내하는 것을
참고해 기본 30초로 두되 환경변수로 조정 가능하게 한다. 결과가 없으면 재시도하도록 안내한다.

### #4 대용량 파일
`result_text`에 파일 전문이 담기므로 큰 파일은 AI Agent의 컨텍스트를 크게 소비한다. 현재는
가공 없이 전달하는 것이 요구사항이므로 자르지 않는다. 필요해지면 후속 과제로 최대 길이 제한
(config 상수)을 추가한다.

### #5 한 호스트에 여러 에이전트
첫 번째 `agent_id`를 사용하고 `notice`로 전체 후보를 안내한다 (4.3절). 실환경에서 호스트당
복수 에이전트가 일반적인 것으로 확인되면, 에이전트를 직접 지정하는 파라미터 추가를 검토한다.

---

## 11. 비기능 요구사항 (CLAUDE.md 그라운드 룰 매핑)

| 룰 | 적용 |
|----|------|
| TDD, 커버리지 85%+ | `tests/read_server_file_mcp/` 3종을 구현보다 먼저 작성하고, `pyproject.toml` 커버리지 대상에 `read_server_file_mcp` 추가 |
| SOLID | 8.1절 |
| 하드코딩 금지 | 경로·테이블/컬럼명·명령 타입·응답 키·메시지·대기 시간 전부 `config.py` 상수 |
| 문서 최신화 | 본 문서 + `README.md`(서버 목록/도구 상세/환경변수/프로젝트 구조) + `.env.example` |

---

## 12. 구현 체크리스트

- [x] `docs/read_server_file_mcp_requirements.md` (본 문서)
- [x] `tests/read_server_file_mcp/test_config.py`
- [x] `tests/read_server_file_mcp/test_client.py`
- [x] `tests/read_server_file_mcp/test_server.py`
- [x] `src/read_server_file_mcp/config.py`
- [x] `src/read_server_file_mcp/client.py`
- [x] `src/read_server_file_mcp/server.py`
- [x] `pyproject.toml` — 엔트리포인트 및 커버리지 대상 추가
- [x] `.env.example` — `READ_SERVER_FILE_RESULT_WAIT_SECONDS` 추가
- [x] `README.md` — 서버 목록 / 도구 상세 / 환경변수 / 프로젝트 구조 갱신
