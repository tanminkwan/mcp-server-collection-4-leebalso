# Config Diff MCP 요구사항 정의서 겸 설계서 (`config_diff_mcp`)

> 상태: **설계 완료 / 구현 대기**. 대상 API 스펙은 실제 서버
> (`https://app.mwm.local:20443`)의 OpenAPI 문서(`GET /api/v1/_openapi`)를 직접 조회해
> `MwDiffDataApi` 태그의 4개 오퍼레이션 정의를 확보한 상태다 (2026-09-08).
>
> ⚠️ **선결 과제 있음**: `/diff_data/*` 4개 경로는 현재 Bearer 토큰으로 접근되지 않고
> 로그인 페이지로 302 리다이렉트된다. 상세와 해결 방안은 [10. Open Issues](#10-open-issues) 참조.
> 이 항목이 해소되어야 구현·검증이 가능하다.
>
> 기존 `email_mcp`, `extract_error_log_mcp`, `error_rag_mcp`와 동일한 스타일(아키텍처, 의존성,
> 환경설정 패턴)로 구성된 독립적인 4번째 MCP 서버로 추가한다.

---

## 1. 개요

### 1.1 목적
미들웨어(WAS/WEB) 설정 파일의 **변경 이력(configuration diff)** 을 AI Agent가 자연어로 조회할 수
있도록 하는 MCP 서버이다.

- WAS 설정(`domain.xml`) 변경 내역 조회
- WEB 설정(`http.m`) 변경 내역 조회

사용자는 `WAS`/`WEB`이라는 구분 대신 **설정 파일명으로 직접 지칭**하기도 한다
(`domain.xml` = WAS, `http.m` = WEB). 두 표현 모두에 반응해야 한다 (3.4절).

장애 분석 시 "언제 무엇이 바뀌었는가"는 1차 원인 후보이므로, 오류 로그 추출
(`extract_error_log_mcp`) · 과거 사례 검색(`error_rag_mcp`)과 함께 사용되는 것을 전제로 한다.

### 1.2 배경 시나리오 (AI Agent 관점)
1. 특정 서버/도메인에서 장애 또는 이상 징후가 탐지된다.
2. AI Agent가 "설정이 최근에 바뀐 적 있나?"를 확인하려 한다.
3. **[본 서버] `get_diff_web` / `get_diff_was`** 로 해당 호스트/도메인의 설정 변경 이력을 조회한다.
4. 반환된 `unified_diff`를 근거로 변경과 장애의 상관관계를 판단한다.
5. (필요 시) `error_rag_mcp`로 과거 유사 사례를 조회하고 조치 결과를 등록한다.

### 1.3 연동 대상 API
`리발소(VER:20260811.001)` 서비스의 `MwDiffDataApi` 태그 REST API 4종을 사용한다.

| # | Method | Path | 용도 |
|---|--------|------|------|
| 1 | GET | `/diff_data/was/list` | WAS 변경 이력 **목록** 조회 |
| 2 | GET | `/diff_data/was/{id}` | WAS 변경 이력 **상세**(new/old/unified_diff) 조회 |
| 3 | GET | `/diff_data/web/list` | WEB 변경 이력 **목록** 조회 |
| 4 | GET | `/diff_data/web/{id}` | WEB 변경 이력 **상세**(new/old/unified_diff) 조회 |

> 같은 서비스에 `MwDiffApi` 태그의 `/diff/was/{id}`, `/diff/web/{id}`(HTML 비교 화면)도 있으나
> 본 서버의 범위가 아니다. 데이터(JSON)를 반환하는 `MwDiffDataApi`만 사용한다.

---

## 2. 기능 요구사항 요약

| 구분 | MCP 도구명 | 대상 API | 설명 |
|------|-----------|----------|------|
| WAS | `get_diff_was` | `/diff_data/was/list` → `/diff_data/was/{id}` | WAS 설정(`domain.xml`) 변경 내역 조회 |
| WEB | `get_diff_web` | `/diff_data/web/list` → `/diff_data/web/{id}` | WEB 설정(`http.m`) 변경 내역 조회 |

- 두 도구 외 추가 기능은 범위에 포함하지 않는다 (단일 책임 원칙 — WAS/WEB 각 1개 함수).
- 두 도구는 **동일한 처리 흐름**을 가지며 대상 리소스(was/web)와 필터 키(`domain_id`/`host_id`)만
  다르다. 이 공통 흐름은 한 곳에 구현하고 두 도구가 파라미터만 달리해 호출한다 (DRY / OCP —
  향후 `db`, `mq` 등 다른 리소스가 추가되어도 흐름 코드는 수정 없이 확장 가능).

---

## 3. 기능 및 도구(Tools) 설계

### 3.1 공통 처리 흐름 (두 도구 동일)

```
[0] 필수 식별자(host_id / domain_id) 검증 — 없거나 공백이면
    API 호출 없이 "되묻기 유도" 응답 반환하고 종료 (3.5절)
      ↓
[1] 입력 날짜 정규화 (4절)
      ↓
[2] GET /diff_data/{resource}/list   (start_date, end_date, {filter_key})
      ↓
[3] 결과 건수 n 에 따라 분기
      ├─ n = 0  → "존재하지 않습니다" 응답 반환 (상세 조회 안 함)
      ├─ n = 1  → 그 1건의 id 로 상세 조회 → 반환 (notice 없음)
      └─ n ≥ 2  → create_on 기준 내림차순 정렬 후 최신 1건의 id 로 상세 조회
                  → 반환 + "전체 n건 중 최근(create_on) 1건만 반환" notice 첨부
      ↓
[4] 상세 응답에서 old 필드 제거 (5.3절)
      ↓
[5] 표준 응답 봉투(6절)에 담아 JSON 문자열로 반환
```

### 3.2 `get_diff_web`
- **목적**: WEB 서버 설정 파일(`http.m`)의 변경 내역을 조회한다.
  사용자가 `web`, `웹`, `웹서버` 대신 **`http.m`** 이라고 지칭해도 이 도구를 사용한다 (3.4절).
- **입력**:

  | 파라미터 | 타입 | 필수 | 설명 |
  |----------|------|------|------|
  | `host_id` | str | **필수** | WEB 호스트 ID. 사용자가 '서버' 또는 '시스템'이라고 부르기도 한다 (예: `paaaa11`). **누락 시 조회하지 않고 사용자에게 되묻는다** (3.5절) |
  | `start_date` | str | 선택 | 조회 시작일 `YYYY-MM-DD` |
  | `end_date` | str | 선택 | 조회 종료일 `YYYY-MM-DD` |

- **동작**: 3.1 공통 흐름을 `resource="web"`, 필터 키 `host_id`로 수행한다.
- **자연어 예시**:
  - `"최근 paaaa11 서버에 web 변경 내역 알려줘"`
    → `get_diff_web(host_id="paaaa11")` (날짜 미지정 = 최근 1건)
  - `"paaaa11 http.m 최근에 바뀐 거 있어?"`
    → `get_diff_web(host_id="paaaa11")` — `http.m`이 WEB 설정을 가리키므로 동일하게 처리
  - `"web 설정 최근 변경 내역 알려줘"` (대상 서버 미지정)
    → **호출하지 않고 사용자에게 "어느 서버(host_id)인지" 되묻는다** (3.5절)

### 3.3 `get_diff_was`
- **목적**: WAS 도메인 설정 파일(`domain.xml`)의 변경 내역을 조회한다.
  사용자가 `was`, `웨스`, `도메인` 대신 **`domain.xml`** 이라고 지칭해도 이 도구를 사용한다 (3.4절).
- **입력**:

  | 파라미터 | 타입 | 필수 | 설명 |
  |----------|------|------|------|
  | `domain_id` | str | **필수** | WAS 도메인 ID (예: `PAAA_Domain`). **누락 시 조회하지 않고 사용자에게 WAS 도메인 ID를 되묻는다** (3.5절) |
  | `start_date` | str | 선택 | 조회 시작일 `YYYY-MM-DD` |
  | `end_date` | str | 선택 | 조회 종료일 `YYYY-MM-DD` |

- **동작**: 3.1 공통 흐름을 `resource="was"`, 필터 키 `domain_id`로 수행한다.
- **자연어 예시**:
  - `"8월11일 was domain PAAA_Domain 설정 변경 내역 알려줘"`
    → `get_diff_was(domain_id="PAAA_Domain", start_date="2026-08-11")`
    → 서버가 `2026-08-10 ~ 2026-08-12`로 확장 (4.2절)
  - `"PAAA_Domain domain.xml 변경 이력 보여줘"`
    → `get_diff_was(domain_id="PAAA_Domain")` — `domain.xml`이 WAS 설정을 가리키므로 동일하게 처리
  - `"was 설정 바뀐 거 있어?"` / `"paaaa11 서버 was 설정 변경 내역"` (도메인 미지정)
    → **호출하지 않고 사용자에게 "WAS 도메인 ID가 무엇인지" 되묻는다** (3.5절).
      후자처럼 서버명만 있는 경우도 마찬가지다 — WAS는 `host_id`로 조회할 수 없다

> ⚠️ **WAS는 `host_id`로 필터링할 수 없다.** `/diff_data/was/list`가 지원하는 필터는 `domain_id`
> 뿐이다. 사용자가 WAS에 대해 서버명(host_id)만 제시한 경우 그 값을 `domain_id`에 넣어서는
> **안 되며**, 사용자에게 WAS 도메인 ID를 되물어야 한다 (3.5절). 도구 설명(docstring)에 이
> 제약을 명시해 AI Agent가 잘못된 값을 넣지 않도록 한다. (10절 Open Issue #2)

### 3.4 설정 파일명 별칭(alias) 처리

사용자는 대상을 `WAS`/`WEB`으로 구분해 말하기도 하지만, **설정 파일명으로 직접 지칭**하는 경우도
많다. 두 표현 모두 동일한 도구로 라우팅되어야 한다.

| 사용자 표현 | 대상 | 도구 |
|-------------|------|------|
| `WAS`, `was`, `웨스`, `도메인`, **`domain.xml`** | WAS 도메인 설정 | `get_diff_was` |
| `WEB`, `web`, `웹`, `웹서버`, **`http.m`** | WEB 서버 설정 | `get_diff_web` |

- **구현 방식**: 별칭 해석은 **도구 선택(tool routing) 단계의 문제**이므로 서버 코드에 문자열
  파싱 로직을 넣지 않는다. 대신 `SERVER_INSTRUCTIONS`와 각 도구의 docstring에 파일명을 명시해
  AI Agent가 올바른 도구를 고르도록 한다 (9절). MCP의 도구 설명이 곧 라우팅 근거이기 때문이며,
  서버에 자연어 파서를 두면 Agent의 판단과 이중으로 어긋날 수 있다.
- **하드코딩 금지**: 파일명은 `config.py`의 `WAS_CONFIG_FILE_NAME = "domain.xml"`,
  `WEB_CONFIG_FILE_NAME = "http.m"` 상수로 관리하고, docstring과 `SERVER_INSTRUCTIONS`를
  이 상수로 포매팅해 생성한다. 향후 파일명이 바뀌거나 별칭이 추가돼도 `config.py`만 수정하면 된다
  (그라운드 룰 3).
- **테스트**: 두 도구의 `description`(docstring)에 각각 `http.m` / `domain.xml` 문자열이
  포함되는지를 검증하는 테스트를 둔다. 별칭이 설명에서 누락되면 AI Agent의 도구 선택이
  조용히 실패하므로, 이를 회귀 테스트로 고정한다.

### 3.5 대상 식별자 누락 시 되묻기 (필수)

`host_id`(WEB) / `domain_id`(WAS)는 **필수**다. 값이 없거나 공백 문자열이면 **API를 호출하지
않고** 사용자에게 되묻도록 유도하는 응답을 반환한다.

- **근거**: 대상 API의 필터 파라미터는 스펙상 선택(optional)이지만, 생략하면 **전체 호스트/전체
  도메인**의 이력이 섞여 조회된다. 이때 "가장 최근 1건"은 사용자가 궁금해하는 서버와 무관한
  엉뚱한 서버의 diff일 가능성이 높다. 조용히 틀린 답을 주는 것보다 되묻는 편이 안전하다.
- **구현**:
  1. 도구 시그니처에서 `host_id` / `domain_id`를 **필수 파라미터**로 선언한다.
  2. 그럼에도 빈 문자열/공백만 전달될 수 있으므로, 서버가 `strip()` 후 비어 있는지 검증한다.
     (`error_rag_mcp`가 빈 `error_keyword`를 가드하는 것과 동일한 패턴)
  3. 검증 실패 시 6.4절의 오류 응답 구조로, **되묻기를 지시하는 메시지**를 반환한다.
- **메시지** (`config.py` 상수로 관리 — 그라운드 룰 3):

  | 상수 | 값 |
  |------|-----|
  | `MISSING_HOST_ID_MESSAGE` | `조회할 WEB 서버의 host_id가 필요합니다. 사용자에게 어느 서버(호스트)의 http.m 변경 내역인지 확인해 주세요.` |
  | `MISSING_DOMAIN_ID_MESSAGE` | `조회할 WAS 도메인 ID(domain_id)가 필요합니다. 사용자에게 어느 WAS 도메인의 domain.xml 변경 내역인지 확인해 주세요. WAS는 서버명(host_id)으로는 조회할 수 없습니다.` |

- 메시지는 AI Agent가 그대로 읽고 사용자에게 질문을 던질 수 있도록 **행동 지시형**으로 작성한다.

---

## 4. 날짜 구간 정규화 규칙

사용자는 (a) 명시적 날짜/구간을 주거나 (b) "최근 변경내역"처럼 날짜 없이 요청한다. 이 두 경우를
하나의 파라미터 쌍(`start_date`, `end_date`)으로 흡수한다.

### 4.1 대상 API의 날짜 동작 (OpenAPI 스펙 원문 기준)
> "시작일(start_date)과 종료일(end_date)이 **모두 없으면** 일자 조건 없이 **가장 최근에 변경된
> 내역 1건만** 조회합니다. 시작일 또는 종료일이 하나라도 지정되면 해당 구간의 전체 내역을 조회합니다."

즉 **"최근 변경내역"은 날짜 파라미터를 아예 보내지 않는 것으로 구현된다.** 서버가 별도의 정렬/
제한 로직을 만들 필요가 없다.

### 4.2 정규화 표

| `start_date` | `end_date` | 처리 | 근거 |
|--------------|------------|------|------|
| 없음 | 없음 | **날짜 파라미터를 전송하지 않음** → API가 최근 1건 반환 | "최근 변경내역" 요청 |
| 있음 | 없음 | 단일 일자로 간주 → `[start-1d, start+1d]` | 사용자가 "8월11일"처럼 하루만 지목 |
| 없음 | 있음 | 단일 일자로 간주 → `[end-1d, end+1d]` | 상동 |
| 있음 | 있음 (동일 값) | 단일 일자로 간주 → `[date-1d, date+1d]` | 상동 |
| 있음 | 있음 (상이) | **그대로 사용** (확장하지 않음) | 사용자가 명시적 구간을 지정한 것이므로 의도를 변경하지 않는다 |

- **여유일수는 하드코딩하지 않는다.** `config.py`의 `DEFAULT_DATE_PADDING_DAYS = 1` 상수로 두고,
  환경변수 `DIFF_DATE_PADDING_DAYS`로 재정의 가능하게 한다 (그라운드 룰 3).
- 확장 사유: 변경 수집 시각과 사용자가 인지한 날짜 사이에 하루 정도의 오차(수집 배치 시점,
  타임존, "어제 바뀐 것 같은데"류의 부정확한 진술)가 흔하기 때문이다.

### 4.3 날짜 형식 검증
- 입력 형식은 `YYYY-MM-DD`(`config.py`의 `DATE_FORMAT` 상수)만 허용한다.
- 형식이 맞지 않으면 API를 호출하지 않고 즉시 오류 메시지를 반환한다.
- **연도 추론은 서버가 하지 않는다.** "8월11일"처럼 연도가 없는 표현을 `YYYY-MM-DD`로 바꾸는 것은
  현재 시각 컨텍스트를 가진 AI Agent의 책임이다. 이 규칙을 도구 docstring에 명시한다.
  (서버가 "가장 가까운 과거의 8월 11일"을 추측하면 연말/연초에 조용히 틀린 결과를 준다.)

---

## 5. API 연동 설계

### 5.1 목록 조회 — `GET /diff_data/{resource}/list`

**Query Parameters** (API 스펙상 모두 선택)

| 파라미터 | web | was | 설명 | MCP 도구에서의 필수 여부 |
|----------|-----|-----|------|--------------------------|
| `start_date` | ✅ | ✅ | 시작일 `YYYY-MM-DD` | 선택 |
| `end_date` | ✅ | ✅ | 종료일 `YYYY-MM-DD` | 선택 |
| `host_id` | ✅ | ❌ | WEB 호스트 ID | **필수** (3.5절) |
| `domain_id` | ❌ | ✅ | WAS 도메인 ID | **필수** (3.5절) |

> API는 `host_id`/`domain_id` 없이도 호출되지만(전체 대상 조회), **MCP 도구 레벨에서는 필수로
> 강제**한다. 근거는 3.5절 참조.

**Response 200** — JSON 배열

```jsonc
// web
[ { "id": 123, "host_id": "paaaa11", "port": 8080, "create_on": "2026-08-11 14:23:01" } ]
// was
[ { "id": 456, "domain_id": "PAAA_Domain", "create_on": "2026-08-11 14:23:01" } ]
```

- 값이 `null`이거나 배열이 아닌 응답이 오는 경우도 **0건과 동일하게** 취급한다(방어적 처리).
- **정렬은 서버(본 MCP)가 직접 수행한다.** 목록 API의 정렬 순서는 스펙에 명시되어 있지 않으므로
  응답 순서를 신뢰하지 않는다. `create_on` 내림차순으로 정렬해 첫 번째를 "가장 최근"으로 삼고,
  `create_on` 파싱이 불가능하거나 동률이면 `id` 내림차순을 2차 기준으로 사용한다.

### 5.2 상세 조회 — `GET /diff_data/{resource}/{id}`

**Path Parameter**: `id` (integer) — 변경 이력 레코드 ID
(`mw_web_change_history` / `mw_was_change_history`)

**Response 200**

| 필드 | web | was | 설명 | MCP 반환 |
|------|-----|-----|------|----------|
| `create_on` | ✅ | ✅ | 변경 일시 | 포함 |
| `host_id` | ✅ | ❌ | WEB 서버 Host ID | 포함 |
| `port` | ✅ | ❌ | WEB 서비스 Port | 포함 |
| `domain_id` | ❌ | ✅ | WAS 도메인 ID | 포함 |
| `new` | ✅ | ✅ | 현재 설정 텍스트 | 포함 |
| `unified_diff` | ✅ | ✅ | Unified Diff 결과 | 포함 |
| `old` | ✅ | ✅ | 이전 설정 텍스트 | **제거 (5.3절)** |

**Response 404**: 해당 ID의 이력을 찾을 수 없음 → 목록에는 있으나 상세가 없는 비정상 상태이므로,
"해당 변경 이력 상세를 찾을 수 없습니다" 오류 메시지로 변환해 반환한다.

### 5.3 `old` 필드 제거 (필수 요구사항)
상세 응답의 `old`(이전 설정 전문)는 **반환하지 않는다.**

- **근거**: `old`는 `new`와 `unified_diff`를 역으로 적용하면 복원 가능한 파생 정보다.
  설정 파일 전문은 수천 라인에 달할 수 있어, 중복 전송 시 AI Agent의 컨텍스트 토큰을 크게 낭비한다.
- **구현 위치**: 클라이언트가 아니라 **도구 함수(server.py) 쪽에서 제거**한다. `DiffClient`는
  API 응답을 가공 없이 그대로 반환하는 단일 책임만 갖는다 (SRP).
- 제거 대상 필드명은 `config.py`의 `EXCLUDED_DETAIL_FIELDS = ("old",)` 상수로 관리한다
  (그라운드 룰 3 — 향후 제외 필드가 늘어나도 상수만 수정).

---

## 6. 응답 형식 설계

AI Agent가 파싱하기 쉽도록 **항상 동일한 구조의 JSON 문자열**을 반환한다. 상황별로 다른 모양의
응답을 주면 Agent가 분기 처리에 실패한다.

### 6.1 0건

```json
{
  "found": false,
  "total_count": 0,
  "message": "존재하지 않습니다."
}
```

### 6.2 1건

```json
{
  "found": true,
  "total_count": 1,
  "notice": null,
  "diff": {
    "id": 123,
    "host_id": "paaaa11",
    "port": 8080,
    "create_on": "2026-08-11 14:23:01",
    "new": "...현재 http.m 전문...",
    "unified_diff": "--- old\n+++ new\n@@ ... @@\n-Timeout 30\n+Timeout 60"
  }
}
```

### 6.3 2건 이상

```json
{
  "found": true,
  "total_count": 3,
  "notice": "전체 3건의 변경 내역이 있습니다. 그 중 가장 최근(2026-08-11 14:23:01) 1건만 반환합니다.",
  "diff": { "...": "위와 동일한 구조" }
}
```

- `notice` 문구는 `config.py`의 `MULTIPLE_RESULT_NOTICE_TEMPLATE` 포맷 문자열 상수로 관리한다
  (그라운드 룰 3).
  예: `"전체 {total_count}건의 변경 내역이 있습니다. 그 중 가장 최근({create_on}) 1건만 반환합니다."`
- 0건 메시지도 `NOT_FOUND_MESSAGE = "존재하지 않습니다."` 상수로 관리한다.
- `diff.id`는 목록 조회 결과의 `id`를 넣어준다(상세 응답 스키마에는 `id`가 없으므로 서버가 주입).
  사용자가 후속으로 특정 이력을 다시 지목할 때 필요하다.

### 6.4 오류

```json
{ "found": false, "total_count": 0, "message": "<오류 사유>" }
```

날짜 형식 오류, 상세 404, HTTP 오류, **식별자 누락(3.5절)** 등 모든 실패는 예외를 그대로 던지지
않고 위 구조로 변환한다. (MCP 도구가 예외를 던지면 AI Agent 쪽에서 원인 파악이 어렵다.)

식별자 누락 예 — AI Agent가 이 메시지를 읽고 사용자에게 되묻는다:

```json
{
  "found": false,
  "total_count": 0,
  "message": "조회할 WAS 도메인 ID(domain_id)가 필요합니다. 사용자에게 어느 WAS 도메인의 domain.xml 변경 내역인지 확인해 주세요. WAS는 서버명(host_id)으로는 조회할 수 없습니다."
}
```

---

## 7. 환경 변수

`/diff_data/*`는 `email_mcp`/`extract_error_log_mcp`와 **동일한 서비스**(`API_BASE_URL`)에 있으므로
기존 `API_*` 환경변수를 재사용한다. 신규 변수는 날짜 여유일수 하나뿐이다.

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `API_BASE_URL` | ✅ | — | 리발소 서비스 base URL (예: `https://app.mwm.local:20443`) |
| `API_BEARER_TOKEN` | ✅ | — | 인증 토큰 (10절 Open Issue #1 확인 필요) |
| `API_SSL_VERIFY` | ❌ | `false` | 사설 인증서 환경 대응 |
| `API_TIMEOUT` | ❌ | `60` | HTTP 타임아웃(초) |
| `DIFF_DATE_PADDING_DAYS` | ❌ | `1` | 단일 일자 지정 시 앞뒤로 확장할 일수 (4.2절) |

`.env.example`에 `DIFF_DATE_PADDING_DAYS`를 추가한다.

`config.py`가 관리할 상수 (하드코딩 금지 — 그라운드 룰 3):

| 상수 | 값 | 용도 |
|------|-----|------|
| `WAS_LIST_PATH` | `/diff_data/was/list` | WAS 목록 경로 |
| `WAS_DETAIL_PATH` | `/diff_data/was/{id}` | WAS 상세 경로 |
| `WEB_LIST_PATH` | `/diff_data/web/list` | WEB 목록 경로 |
| `WEB_DETAIL_PATH` | `/diff_data/web/{id}` | WEB 상세 경로 |
| `WAS_FILTER_KEY` | `domain_id` | WAS 목록 필터 파라미터명 |
| `WEB_FILTER_KEY` | `host_id` | WEB 목록 필터 파라미터명 |
| `WAS_CONFIG_FILE_NAME` | `domain.xml` | WAS 설정 파일명 — 도구 설명/별칭 (3.4절) |
| `WEB_CONFIG_FILE_NAME` | `http.m` | WEB 설정 파일명 — 도구 설명/별칭 (3.4절) |
| `DATE_FORMAT` | `%Y-%m-%d` | 날짜 입출력 형식 |
| `DEFAULT_DATE_PADDING_DAYS` | `1` | 여유일수 기본값 |
| `EXCLUDED_DETAIL_FIELDS` | `("old",)` | 상세 응답 제외 필드 |
| `NOT_FOUND_MESSAGE` | `존재하지 않습니다.` | 0건 메시지 |
| `MISSING_HOST_ID_MESSAGE` | (3.5절) | `host_id` 누락 시 되묻기 유도 메시지 |
| `MISSING_DOMAIN_ID_MESSAGE` | (3.5절) | `domain_id` 누락 시 되묻기 유도 메시지 |
| `MULTIPLE_RESULT_NOTICE_TEMPLATE` | (6.3절) | 다건 안내 문구 |
| `DEFAULT_SSL_VERIFY` / `DEFAULT_TIMEOUT` | `False` / `60` | 기존 서버와 동일 |

---

## 8. 프로젝트 구조 (예정)

```
src/config_diff_mcp/
├── __init__.py
├── config.py     # Settings + 경로/문구/형식 상수
├── client.py     # DiffClient — HTTP 호출만 담당 (가공 없음)
└── server.py     # MCP 서버, get_diff_was / get_diff_web 도구, 날짜 정규화·분기·응답 조립

tests/config_diff_mcp/
├── __init__.py
├── test_config.py   # 환경변수 로딩, URL 조합, 여유일수 파싱
├── test_client.py   # respx 로 목록/상세 HTTP 호출 검증 (파라미터 조합, 404)
└── test_server.py   # 0건/1건/n건 분기, 날짜 정규화 표, old 제거, 정렬, 오류 응답
```

`pyproject.toml`에 추가:
- `[project.scripts]` → `config-diff-mcp = "config_diff_mcp.server:main"`
- `addopts` 커버리지 대상 → `--cov=config_diff_mcp` 추가
- `[tool.coverage.run] source` → `src/config_diff_mcp` 추가

### 8.1 모듈 책임 (SOLID)
- **`config.py`**: 설정·상수의 단일 출처. 다른 모듈은 리터럴을 갖지 않는다. (SRP, 그라운드 룰 3)
- **`client.py`**: `DiffClient`. `Settings`를 **주입받아** 인증/SSL/타임아웃을 처리하고
  `list_diffs(resource, params)` / `get_diff_detail(resource, id)` 두 메서드만 노출한다.
  응답을 가공하지 않는다. (SRP, DIP — `Settings` 구체 타입이 아닌 인터페이스 계약에 의존)
- **`server.py`**: 날짜 정규화 → 목록 조회 → 건수 분기 → 상세 조회 → `old` 제거 → 응답 조립.
  `get_diff_was`/`get_diff_web`은 공통 함수 `_get_diff(resource, filter_key, filter_value, ...)`에
  파라미터만 달리 위임한다. (OCP — 리소스 추가 시 상수와 얇은 래퍼만 추가)

---

## 9. MCP 서버 메타데이터 (AI Agent 사용성)

- `SERVER_NAME`: `config-diff-mcp`
- `SERVER_INSTRUCTIONS` (요지):
  > WAS/WEB 미들웨어 설정 파일의 변경 이력을 조회하는 MCP 서버입니다.
  > WAS 도메인 설정(`domain.xml`) 변경은 `get_diff_was`, WEB 서버 설정(`http.m`) 변경은
  > `get_diff_web`을 사용하세요. **사용자는 WAS/WEB이라는 말 대신 설정 파일명으로 지칭하기도
  > 합니다 — `domain.xml`이라고 하면 `get_diff_was`, `http.m`이라고 하면 `get_diff_web`입니다.**
  > "최근 ~ 서버 web 설정 바뀐 거 있어?", "8월 11일 WAS 도메인 설정 변경 내역 알려줘",
  > "paaaa11 http.m 언제 바뀌었어?", "PAAA_Domain domain.xml 변경 이력 보여줘" 같은 요청이
  > 트리거입니다.
  > **조회 대상은 반드시 지정해야 합니다** — `get_diff_web`은 `host_id`(서버/시스템),
  > `get_diff_was`는 `domain_id`(WAS 도메인)가 필수입니다. 사용자가 대상을 말하지 않았다면
  > 추측하거나 비워서 호출하지 말고 사용자에게 되물으세요. 특히 WAS는 서버명으로 조회할 수 없어,
  > 서버명만 알고 있다면 WAS 도메인 ID를 사용자에게 확인해야 합니다.
  > 날짜를 언급하지 않으면 `start_date`/`end_date`를 비워 호출하세요 — 가장 최근 1건이 반환됩니다.
  > 날짜는 반드시 `YYYY-MM-DD` 형식으로 변환해 전달해야 하며, 연도를 사용자가 말하지 않았다면
  > 현재 시각을 기준으로 Agent가 판단해 채워야 합니다.
- 도구 docstring에 반드시 포함할 내용:
  - **대상 설정 파일명** — `get_diff_was`는 `domain.xml`, `get_diff_web`은 `http.m`.
    사용자가 파일명으로만 지칭해도 해당 도구가 선택되도록 하는 근거이다 (3.4절)
  - `host_id`는 사용자가 '서버' 또는 '시스템'이라고 부르기도 한다는 점
  - **`host_id`/`domain_id`는 필수**이며, 모르면 추측하지 말고 사용자에게 되물어야 한다는 점 (3.5절)
  - **WAS는 `domain_id`만 필터 가능**하고 `host_id`로는 조회할 수 없다는 점 (3.3절)
  - 하루만 지목하면 서버가 앞뒤 1일씩 확장해 조회한다는 점
  - 응답에 `old`(이전 설정 전문)가 포함되지 않으며, 필요하면 `new`와 `unified_diff`로 복원하라는 점
  - `total_count ≥ 2`일 때 `notice`가 채워지며 최신 1건만 담긴다는 점

---

## 10. Open Issues

### #1 (필수 선결) `/diff_data/*`가 Bearer 토큰으로 접근되지 않음
**현상** (2026-09-08 실측):

| 요청 | 결과 |
|------|------|
| `GET /api/v1/_openapi` (토큰 없음) | `401` |
| `GET /api/v1/_openapi` (Bearer 토큰) | `200 application/json` — 토큰 유효 확인 |
| `GET /api/v1/knowledge/mdcontent/list` (Bearer 토큰) | `200` — 기존 서버 정상 동작 확인 |
| `GET /diff_data/web/list` (Bearer 토큰) | `302 → /login/?next=...` + `Set-Cookie: session=...` |
| `GET /api/v1/diff_data/web/list` (Bearer 토큰) | 404 HTML (해당 경로 없음) |

**해석**: 토큰 자체는 유효하나, `/diff_data/*`는 JWT를 검증하는 `/api/v1` API 블루프린트가 아니라
**세션 로그인(Flask-AppBuilder `@has_access`)으로 보호되는 루트 경로**에 등록되어 있다.
OpenAPI 문서에는 `security: [{ jwt: [] }]`로 선언되어 있으나 실제 동작과 불일치한다.

**해결 방안 (선호 순)**:
1. **(권장) 서버 측 수정** — `/diff_data/*`를 `/api/v1` 아래 JWT 인증 API로 노출하거나
   `@has_access` → `@has_access_api`(또는 `protect()`)로 교체한다. 기존 3개 MCP 서버와 동일한
   인증 방식을 유지할 수 있어 `config.py`/`client.py`가 단순해진다.
2. **세션 로그인 방식 지원** — MCP 서버가 `/login/`에 ID/PW로 로그인해 세션 쿠키를 유지하고
   그 쿠키로 `/diff_data/*`를 호출한다. `DIFF_API_USERNAME`/`DIFF_API_PASSWORD` 환경변수와
   쿠키 수명 관리·재로그인 로직이 추가로 필요해 복잡도가 올라간다.
3. **`/api/v1/security/login`으로 JWT 재발급** — 다만 세션 보호 경로는 JWT를 보지 않으므로
   이 방법만으로는 해결되지 않을 가능성이 높다. 1번과 병행 검토.

**결정 필요**: 위 3안 중 어느 방향으로 갈지 확정되어야 `config.py`/`client.py`의 인증 설계가
확정된다. 본 문서의 7절은 **1안(JWT)** 을 전제로 작성되어 있다.

### #2 WAS 조회 시 `host_id → domain_id` 매핑
사용자가 WAS에 대해 서버명만 말하는 경우(`"paaaa11 서버 WAS 설정 변경 내역"`) `/diff_data/was/list`는
`host_id` 필터를 지원하지 않아 조회할 수 없다.

- **현재 설계 (확정)**: 매핑을 제공하지 않는다. `domain_id`를 **필수 파라미터**로 두고, 누락 시
  `MISSING_DOMAIN_ID_MESSAGE`로 **사용자에게 WAS 도메인 ID를 되묻도록 유도**한다 (3.5절).
  서버명을 `domain_id`에 그대로 넣는 오용을 막기 위해 도구 설명에도 제약을 명시한다.
- **대안(범위 밖)**: 호스트→도메인 매핑 API가 별도로 존재한다면 이를 조회하는 단계를 추가할 수
  있다. 해당 API 존재 여부 확인 필요.

### #3 `create_on` 문자열 형식 미확정
OpenAPI 스펙상 `create_on`은 `type: string`으로만 정의되어 있고 실제 포맷(`YYYY-MM-DD HH:MM:SS`
vs ISO-8601)은 #1 때문에 실제 응답으로 확인하지 못했다.

- **대응**: 정렬 시 여러 포맷을 시도하고, 전부 실패하면 **문자열 비교로 fallback**한 뒤
  최종적으로 `id` 내림차순을 사용한다. 파싱 실패가 예외로 이어지지 않게 한다.
- #1 해소 후 실제 응답으로 포맷을 확인하고 본 절과 구현을 갱신한다.

### #4 목록 조회 결과의 최대 건수
`/diff_data/*/list`에 `limit`/페이징 파라미터가 없어, 넓은 날짜 구간을 지정하면 매우 많은 레코드가
반환될 수 있다. 본 서버는 목록의 `id`/`create_on`만 사용하고 상세는 1건만 조회하므로 AI Agent 쪽
토큰 낭비는 없으나, 서버 응답 지연 가능성은 있다. #1 해소 후 실측하여 필요 시 날짜 구간 상한
(예: `MAX_DATE_RANGE_DAYS`) 도입을 검토한다.

---

## 11. 비기능 요구사항 (CLAUDE.md 그라운드 룰 매핑)

| 룰 | 적용 방안 |
|----|-----------|
| **1. TDD** | `tests/config_diff_mcp/` 테스트를 먼저 작성 후 구현. `respx`로 HTTP를 모킹해 0건/1건/n건 분기, 날짜 정규화 표(4.2절)의 5개 케이스, `old` 제거, 정렬 fallback, 404·형식오류 응답을 모두 커버. 라인 커버리지 **85% 이상** 유지 (`--cov-fail-under=85`) |
| **2. SOLID** | 8.1절 모듈 책임 참조. 특히 `DiffClient`는 호출만, 가공은 `server.py` (SRP) / 리소스 추가 시 상수+래퍼만 추가 (OCP) / `Settings` 주입 (DIP) |
| **3. 하드코딩 금지** | 경로·필터 키·날짜 형식·여유일수·제외 필드·안내 문구를 전부 `config.py` 상수 또는 환경변수로 관리 (7절 표) |
| **4. 문서 최신화** | 구현 시 `docs/architecture.md`(4번째 서버 섹션 추가), `docs/usage.md`(환경변수·도구 목록), `docs/installation-guide.md`, `docs/windows-deployment-guide.md`, `README.md`, `.env.example`을 함께 갱신 |

---

## 12. 구현 체크리스트

- [ ] Open Issue #1 인증 방식 확정 (**선결**)
- [ ] `tests/config_diff_mcp/test_config.py` 작성 → `src/config_diff_mcp/config.py` 구현
- [ ] `tests/config_diff_mcp/test_client.py` 작성 → `src/config_diff_mcp/client.py` 구현
- [ ] `tests/config_diff_mcp/test_server.py` 작성 → `src/config_diff_mcp/server.py` 구현
      (도구 설명에 `domain.xml` / `http.m` 별칭이 포함되는지 검증 — 3.4절,
       `host_id`/`domain_id` 누락·공백 시 API 호출 없이 되묻기 메시지 반환 검증 — 3.5절)
- [ ] `pyproject.toml` 엔트리포인트·커버리지 대상 추가
- [ ] `.env.example`에 `DIFF_DATE_PADDING_DAYS` 추가
- [ ] 실제 서버 대상 end-to-end 검증 (`create_on` 포맷 확인 → #3 갱신)
- [ ] `architecture.md` / `usage.md` / `installation-guide.md` / `windows-deployment-guide.md` /
      `README.md` 갱신
- [ ] 전체 테스트 통과 및 커버리지 85% 이상 확인
