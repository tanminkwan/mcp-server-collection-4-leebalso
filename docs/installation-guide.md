# Email MCP Server — 오프라인 설치 및 사용 가이드

> 인터넷이 차단된 환경의 개인 PC(Windows)에서  
> VS Code + Claude 확장을 통해 이메일 발송 MCP 서버를 사용하는 전체 과정을 안내합니다.

---

## 목차

1. [사전 준비 (인터넷 가능한 PC에서)](#1-사전-준비-인터넷-가능한-pc에서)
2. [오프라인 PC에 파일 전송](#2-오프라인-pc에-파일-전송)
3. [Python 설치](#3-python-설치)
4. [프로젝트 설치](#4-프로젝트-설치)
5. [환경변수 설정](#5-환경변수-설정)
6. [VS Code 설정](#6-vs-code-설정)
7. [동작 확인](#7-동작-확인)
8. [MCP 도구 사용법](#8-mcp-도구-사용법)
9. [문제 해결](#9-문제-해결)

---

## 1. 사전 준비 (인터넷 가능한 PC에서)

인터넷이 되는 PC에서 아래 파일들을 미리 다운로드한다.

### 1-1. Python 설치 파일 다운로드

Windows용 Python 3.14 임베디드 패키지 또는 설치파일을 다운로드한다.

```
https://www.python.org/downloads/
```

- Windows: `python-3.14.x-amd64.exe` (64bit 설치파일)
- Linux: `Python-3.14.x.tar.xz` (소스) 또는 배포판 패키지

> **권장**: Windows 설치파일(.exe)을 사용하면 PATH 등록까지 한 번에 처리된다.

### 1-2. Python 패키지 오프라인 번들 생성

인터넷이 되는 PC에서 대상 OS(배포 환경)에 맞는 wheel 파일을 다운로드한다.

**배포 환경이 Windows인 경우 (크로스 플랫폼 다운로드):**
Linux 등 다른 OS에서 Windows 배포용 패키지를 다운로드하려면 `--platform` 옵션을 명시해야 한다.
```bash
# 프로젝트 디렉토리에서 실행
pip download --platform win_amd64 --python-version 3.14 --only-binary=:all: -d ./offline-packages-win .
pip download --platform win_amd64 --python-version 3.14 --only-binary=:all: -d ./offline-packages-win ".[dev]"
```

**배포 환경이 현재 OS와 동일한 경우:**
```bash
# 프로젝트 디렉토리에서 실행
pip download -d ./offline-packages .
pip download -d ./offline-packages ".[dev]"
```

또는 requirements.txt로 추출 후 다운로드:

```bash
pip freeze > requirements-freeze.txt
pip download -d ./offline-packages -r requirements-freeze.txt
```

지정한 디렉토리(`offline-packages-win/` 또는 `offline-packages/`)에 타겟 OS용 `.whl` 파일들이 저장된다.

### 1-3. VS Code 확장 다운로드

VS Code 마켓플레이스에서 `.vsix` 파일을 직접 다운로드한다.

| 확장 | 다운로드 URL |
|------|-------------|
| Claude (Anthropic) | https://marketplace.visualstudio.com/items?itemName=anthropics.claude-code → **Download Extension** |

> `.vsix` 파일을 저장한다.

### 1-4. 전송할 파일 목록 정리

```
email-mcp-server/            ← 프로젝트 전체 (이 저장소)
├── src/
├── tests/
├── docs/
├── pyproject.toml
├── .env.example
├── ...
├── offline-packages-win/     ← pip download로 생성한 Windows 배포용 wheel 파일들 (또는 offline-packages/)
python-3.14.x-amd64.exe      ← Python 설치파일
claude-code-x.x.x.vsix       ← VS Code 확장 파일
```

---

## 2. 오프라인 PC에 파일 전송

USB 드라이브 또는 내부 파일 서버를 통해 위 파일들을 오프라인 PC로 복사한다.

**권장 경로:**

| 항목 | Windows 경로 | Linux 경로 |
|------|-------------|-----------|
| 프로젝트 | `C:\projects\email-mcp-server` | `~/projects/email-mcp-server` |
| Python 설치파일 | `C:\temp\python-3.14.x-amd64.exe` | — |
| VS Code 확장 | `C:\temp\claude-code-x.x.x.vsix` | — |

---

## 3. Python 설치

### Windows

1. `python-3.14.x-amd64.exe` 실행
2. **반드시 체크**: `☑ Add python.exe to PATH`
3. **Install Now** 클릭
4. 설치 완료 후 확인:

```cmd
python --version
```

출력 예시: `Python 3.14.3`

### Linux (Ubuntu/Debian)

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.14 python3.14-venv python3.14-dev
```

> 오프라인 환경이면 `.deb` 패키지를 미리 다운로드하여 `dpkg -i` 로 설치한다.

---

## 4. 프로젝트 설치

### 4-1. 가상환경 생성

**Windows (cmd):**

```cmd
cd C:\projects\email-mcp-server
python -m venv .venv
.venv\Scripts\activate
```

**Windows (PowerShell):**

```powershell
cd C:\projects\email-mcp-server
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> PowerShell 실행 정책 에러 발생 시:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

**Linux:**

```bash
cd ~/projects/email-mcp-server
python3.14 -m venv .venv
source .venv/bin/activate
```

### 4-2. 오프라인 패키지 설치

```bash
# Windows 배포용 패키지를 다운로드한 경우
pip install --no-index --find-links=./offline-packages-win -e .

# 배포 환경과 동일한 OS에서 다운로드한 경우
# pip install --no-index --find-links=./offline-packages -e .
```

설치 확인:

```bash
pip list | grep mcp-server-collection
```

출력 예시: `mcp-server-collection  0.1.0  /path/to/email-mcp-server`

### 4-3. 설치 검증

```bash
email-mcp --help
extract-error-log-mcp --help
error-rag-mcp --help
config-diff-mcp --help
```

또는 Python으로 직접 실행 확인:

```bash
python -c "from email_mcp.server import create_server; print('OK')"
python -c "from extract_error_log_mcp.server import create_server; print('OK')"
python -c "from error_rag_mcp.server import create_server; print('OK')"
python -c "from config_diff_mcp.server import create_server; print('OK')"
```

---

## 5. 환경변수 설정

### 5-1. .env 파일 생성

```bash
cp .env.example .env
```

### 5-2. .env 파일 편집

`.env` 파일을 텍스트 편집기로 열어 실제 값을 입력한다.

```env
API_BASE_URL=https://app.mwm.local:20443
API_BEARER_TOKEN=여기에_실제_JWT_토큰_입력
API_SSL_VERIFY=false
# 선택: 수신자 이름 매핑 (JSON 또는 이름:이메일 콤마 구분)
EMAIL_RECIPIENT_MAPPING=홍길동:hong@example.com, 김철수:kim@example.com
# 선택: 설정 변경 이력 조회 시 단일 일자 앞뒤 확장 일수 (config-diff-mcp 전용)
DIFF_DATE_PADDING_DAYS=1
```

| 변수 | 설명 | 필수 | 기본값 |
|------|------|:----:|--------|
| `API_BASE_URL` | EmailApi/로그 추출/변경 이력 API 서버 주소 | O | — |
| `API_BEARER_TOKEN` | JWT 인증 토큰 | O | — |
| `API_SSL_VERIFY` | SSL 인증서 검증 여부 | X | `false` |
| `API_TIMEOUT` | HTTP 요청 타임아웃(초) | X | `60` |
| `EMAIL_RECIPIENT_MAPPING` | 수신자 이름-이메일 매핑 (`email-mcp` 전용) | X | — |
| `DIFF_DATE_PADDING_DAYS` | 단일 일자 지정 시 앞뒤 확장 일수 (`config-diff-mcp` 전용) | X | `1` |

> 위 표는 `email-mcp`/`extract-error-log-mcp`/`config-diff-mcp`가 공유하는 환경변수이다.
> `error-rag-mcp`만 별도의 `RAG_*` 환경변수를 사용한다
> ([5-5. Error RAG MCP 환경변수](#5-5-error-rag-mcp-환경변수) 참조).

### 5-3. JWT 토큰 발급

리발소 웹에서 장기 토큰을 발급받는다:

```
https://app.mwm.local:20443/common/generate_long_term_token
```

> 토큰은 `.env` 파일에만 저장하고, 절대 코드에 직접 삽입하지 않는다.

### 5-4. 수신자 이름 매핑 설정 (선택)

`EMAIL_RECIPIENT_MAPPING` 환경변수를 설정하면 이메일 발송 시 `receivers`에 이메일 주소 대신 사람 이름만 전달해도 서버가 매핑된 이메일 주소로 자동 변환합니다.

- **콤마/콜론 구분 형식 (권장)**: `EMAIL_RECIPIENT_MAPPING=홍길동:hong@example.com, 김철수:kim@example.com`
- **JSON 형식**: `EMAIL_RECIPIENT_MAPPING={"홍길동": "hong@example.com", "김철수": "kim@example.com"}`
- 매핑되지 않은 이름이 전달될 경우, 도구는 사용자에게 이메일 주소를 찾을 수 없다는 에러 메시지를 반환합니다.

### 5-5. Error RAG MCP 환경변수

`error-rag-mcp`는 llm-agent RAG API와 통신하며, 위 `API_*`/`EMAIL_*` 변수와는 완전히 별도인
`RAG_*` 환경변수를 사용한다. 같은 `.env` 파일에 아래 값을 추가하면 된다.

```env
RAG_API_BASE_URL=http://localhost:28000
# 선택: 현재 llm-agent는 API Key 없이 접근 가능. 인증이 필요해지면 설정.
RAG_API_BEARER_TOKEN=
RAG_API_SSL_VERIFY=false
RAG_COLLECTION_NAME=여기에_실제_콜렉션_ID_입력
RAG_DOMAIN_ID=여기에_실제_도메인_ID_입력
RAG_VECTOR_SEARCH_LIMIT=3
RAG_TEXT_MATCHING_LIMIT=2
RAG_SOURCE=error-resolution-report
```

| 변수 | 설명 | 필수 | 기본값 |
|------|------|:----:|--------|
| `RAG_API_BASE_URL` | llm-agent 서비스 기본 URL | O | — |
| `RAG_API_BEARER_TOKEN` | 인증 토큰 (현재 미인증 접근 가능) | X | — (헤더 생략) |
| `RAG_API_SSL_VERIFY` | SSL 인증서 검증 여부 | X | `false` |
| `RAG_COLLECTION_NAME` | 고정 콜렉션 식별자 | O | — |
| `RAG_DOMAIN_ID` | 고정 도메인 ID (정수) | O | — |
| `RAG_VECTOR_SEARCH_LIMIT` | 벡터 검색 결과 개수 | X | `3` |
| `RAG_TEXT_MATCHING_LIMIT` | 텍스트 매칭 검색 결과 개수 | X | `2` |
| `RAG_SOURCE` | 등록 시 지식의 `source` 태그 | X | `error-resolution-report` |

> `RAG_COLLECTION_NAME`/`RAG_DOMAIN_ID`는 llm-agent의 `/api/collections`, `/api/domains` API로
> 미리 생성해둔 값이어야 한다. 상세 설계 근거는 [error_rag_mcp 요구사항 정의서](error_rag_mcp_requirements.md) 참조.

---

## 6. VS Code 설정

### 6-1. Claude 확장 설치 (오프라인)

VS Code에서 `Ctrl+Shift+P` → **Extensions: Install from VSIX...** 선택 → `.vsix` 파일 지정.

### 6-2. MCP 서버 설정

VS Code에서 MCP 서버를 등록하는 방법은 두 가지이다.  
환경변수를 설정하는 방식에 따라 택일한다.

---

#### 방법 A: `.env` 파일 사용

프로젝트 루트에 `.env` 파일이 있으면 MCP 서버가 자동으로 로드한다.  
`.vscode/mcp.json`에는 command만 지정하면 된다.

**Windows:**

```json
{
  "servers": {
    "email-mcp": {
      "type": "stdio",
      "command": "C:\\projects\\email-mcp-server\\.venv\\Scripts\\email-mcp.exe"
    }
  }
}
```

**Linux:**

```json
{
  "servers": {
    "email-mcp": {
      "type": "stdio",
      "command": "/home/사용자명/projects/email-mcp-server/.venv/bin/email-mcp"
    }
  }
}
```

> `.env` 파일 생성 방법은 [5. 환경변수 설정](#5-환경변수-설정) 참조.

---

#### 방법 B: `mcp.json`의 `env` 필드에서 직접 설정 (권장)

`.env` 파일 없이 `mcp.json`에서 환경변수를 직접 전달할 수 있다.  
**다른 프로젝트의 VS Code에서 이 MCP 서버를 사용할 때 특히 유용하다.**

**Windows:**

```json
{
  "servers": {
    "email-mcp": {
      "type": "stdio",
      "command": "C:\\projects\\email-mcp-server\\.venv\\Scripts\\email-mcp.exe",
      "env": {
        "API_BASE_URL": "https://app.mwm.local:20443",
        "API_BEARER_TOKEN": "your_jwt_token_here",
        "API_SSL_VERIFY": "false"
      }
    }
  }
}
```

**Linux:**

```json
{
  "servers": {
    "email-mcp": {
      "type": "stdio",
      "command": "/home/사용자명/projects/email-mcp-server/.venv/bin/email-mcp",
      "env": {
        "API_BASE_URL": "https://app.mwm.local:20443",
        "API_BEARER_TOKEN": "your_jwt_token_here",
        "API_SSL_VERIFY": "false"
      }
    }
  }
}
```

> **참고**: `env`에 설정한 값이 `.env` 파일보다 우선한다. 두 방법을 혼용할 수도 있다.

---

#### 방법 C: 사용자 전역 설정 (모든 프로젝트에서 사용)

VS Code `settings.json` (`Ctrl+Shift+P` → **Preferences: Open User Settings (JSON)**)에 등록하면 모든 프로젝트에서 사용할 수 있다.

**Windows:**

```json
{
  "mcp": {
    "servers": {
      "email-mcp": {
        "type": "stdio",
        "command": "C:\\projects\\email-mcp-server\\.venv\\Scripts\\email-mcp.exe",
        "env": {
          "API_BASE_URL": "https://app.mwm.local:20443",
          "API_BEARER_TOKEN": "your_jwt_token_here",
          "API_SSL_VERIFY": "false"
        }
      }
    }
  }
}
```

**Linux:**

```json
{
  "mcp": {
    "servers": {
      "email-mcp": {
        "type": "stdio",
        "command": "/home/사용자명/projects/email-mcp-server/.venv/bin/email-mcp",
        "env": {
          "API_BASE_URL": "https://app.mwm.local:20443",
          "API_BEARER_TOKEN": "your_jwt_token_here",
          "API_SSL_VERIFY": "false"
        }
      }
    }
  }
}
```

#### 참고: 여러 MCP 서버 동시 등록

`servers`(또는 `mcp.servers`) 객체에 키를 추가하면 `extract-error-log-mcp`, `error-rag-mcp`도
같은 `mcp.json`에서 함께 등록할 수 있다 (Linux 예시, 방법 B 기준):

```json
{
  "servers": {
    "email-mcp": {
      "type": "stdio",
      "command": "/home/사용자명/projects/email-mcp-server/.venv/bin/email-mcp",
      "env": {
        "API_BASE_URL": "https://app.mwm.local:20443",
        "API_BEARER_TOKEN": "your_jwt_token_here"
      }
    },
    "extract-error-log-mcp": {
      "type": "stdio",
      "command": "/home/사용자명/projects/email-mcp-server/.venv/bin/extract-error-log-mcp",
      "env": {
        "API_BASE_URL": "https://app.mwm.local:20443",
        "API_BEARER_TOKEN": "your_jwt_token_here"
      }
    },
    "error-rag-mcp": {
      "type": "stdio",
      "command": "/home/사용자명/projects/email-mcp-server/.venv/bin/error-rag-mcp",
      "env": {
        "RAG_API_BASE_URL": "http://localhost:28000",
        "RAG_COLLECTION_NAME": "여기에_실제_콜렉션_ID_입력",
        "RAG_DOMAIN_ID": "여기에_실제_도메인_ID_입력"
      }
    },
    "config-diff-mcp": {
      "type": "stdio",
      "command": "/home/사용자명/projects/email-mcp-server/.venv/bin/config-diff-mcp",
      "env": {
        "API_BASE_URL": "https://app.mwm.local:20443",
        "API_BEARER_TOKEN": "your_jwt_token_here"
      }
    }
  }
}
```

> `email-mcp`/`extract-error-log-mcp`/`config-diff-mcp`는 `API_*` 변수를, `error-rag-mcp`는
> `RAG_*` 변수를 쓴다는 점만 다르고 등록 방식은 동일하다.

---

## 7. 동작 확인

### 7-1. MCP 서버 연결 확인

1. VS Code에서 Claude 채팅 패널을 연다
2. MCP 서버 목록에 **email-mcp**(및 등록한 경우 **extract-error-log-mcp**, **error-rag-mcp**, **config-diff-mcp**)가 표시되는지 확인한다
3. 도구 목록에 `send_html_email`, `send_markdown_email`(그리고 등록한 서버의 도구)이 보이면 정상

### 7-2. 테스트 이메일 발송

Claude 채팅에서 다음과 같이 입력:

```
tiffanie.kim@samsung.com 에게 테스트 이메일 보내줘.
제목은 "MCP 서버 테스트"이고, 본문은 간단한 인사말로 작성해.
```

Claude가 `send_html_email` 또는 `send_markdown_email` 도구를 호출하여 이메일을 발송한다.

### 7-3. 커맨드라인에서 직접 테스트

가상환경을 활성화한 후:

```bash
python scripts/send_test_email.py
```

---

## 8. MCP 도구 사용법

### send_html_email

HTML 형식의 이메일을 발송한다.

| 파라미터 | 타입 | 필수 | 설명 | 예시 |
|----------|------|:----:|------|------|
| `receivers` | string | O | 수신자 이름 또는 이메일 (등록된 이름 자동 변환, 콤마로 다수 지정) | `"홍길동, direct@example.com"` |
| `subject` | string | O | 메일 제목 | `"[알림] 점검 안내"` |
| `content` | string | O | 메일 본문 (HTML) | `"<h1>안내</h1><p>내용</p>"` |
| `sender_name` | string | X | 발신인 표시 이름 | `"시스템 관리자"` |

### send_markdown_email

Markdown 본문을 HTML로 변환하여 발송한다.  
Mermaid 다이어그램, 코드 블록, 표 등이 자동 변환된다.

| 파라미터 | 타입 | 필수 | 설명 | 예시 |
|----------|------|:----:|------|------|
| `receivers` | string | O | 수신자 이름 또는 이메일 (등록된 이름 자동 변환, 콤마로 다수 지정) | `"홍길동"` |
| `subject` | string | O | 메일 제목 | `"[보고서] 점검 결과"` |
| `content` | string | O | 메일 본문 (Markdown) | `"# 제목\n- 항목1\n- 항목2"` |
| `sender_name` | string | X | 발신인 표시 이름 | `"리발소 시스템"` |


### 사용 예시 (Claude 채팅)

```
다음 내용을 Markdown 이메일로 보내줘:
- 수신자: user@example.com
- 제목: 주간 보고서
- 내용:
  # 주간 보고
  ## 완료 항목
  - 서버 점검 완료
  - 인증서 갱신
  ## 예정 항목
  - DB 백업 정책 검토
```

### search_similar_error (error-rag-mcp)

오류 요약(벡터 검색)과 오류 코드 등 핵심 키워드(텍스트 매칭 검색)를 함께 사용해 과거 유사
오류/조치 사례를 검색한다.

| 파라미터 | 타입 | 필수 | 설명 | 예시 |
|----------|------|:----:|------|------|
| `error_summary` | string | O | 오류 내용 요약 (300자 이내) | `"DB 커넥션 풀 고갈로 응답 지연 발생"` |
| `error_keyword` | string | O | 오류 코드 등 핵심 식별 키워드 (없으면 빈 문자열 — 이 경우 텍스트 매칭 검색은 건너뛰고 벡터 검색만 수행) | `"ORA-00001"` |

### register_error_resolution (error-rag-mcp)

조치가 끝난 오류와 그 조치 결과를 표준 보고서 형식으로 RAG에 등록한다.

| 파라미터 | 타입 | 필수 | 설명 | 예시 |
|----------|------|:----:|------|------|
| `error_summary` | string | O | 오류 내용 요약 (300자 이내) | `"DB 커넥션 풀 고갈로 응답 지연 발생"` |
| `error_keyword` | list[string] | O | 핵심 식별 키워드 목록 (최대 3개) | `["ORA-00001", "CONN_POOL_EXHAUSTED"]` |
| `error_occurred_at` | string | O | 오류 발생일시 | `"2026-09-03 10:00:00"` |
| `host_id` | string | O | 오류가 발생한 호스트 ID ('서버'/'시스템'이라고도 부름) | `"pcbkaa11"` |
| `was_instance_id` | string | O | 오류가 발생한 WAS 인스턴스 ID (보통 `_MS` 포함) | `"ONL_MS12"` |
| `error_content` | string | O | 오류 내용 (상세) | `"DB 커넥션 풀 고갈"` |
| `action_taken_at` | string | O | 조치일시 | `"2026-09-03 10:30:00"` |
| `actor` | string | O | 조치자 | `"김철수"` |
| `action_content` | string | O | 조치 내용 | `"커넥션 풀 크기 확장"` |

### get_diff_web / get_diff_was (config-diff-mcp)

WEB 서버 설정(`http.m`) 또는 WAS 도메인 설정(`domain.xml`)의 변경 내역을 조회한다.
사용자가 `web`/`was` 대신 파일명(`http.m`/`domain.xml`)으로 지칭해도 같은 도구를 사용한다.

| 파라미터 | 타입 | 필수 | 설명 | 예시 |
|----------|------|:----:|------|------|
| `host_id` | string | O | (`get_diff_web`) WEB 호스트 ID. '서버'/'시스템'이라고도 부름 | `"paaaa11"` |
| `domain_id` | string | O | (`get_diff_was`) WAS 도메인 ID. **서버명으로는 조회 불가** | `"PAAA_Domain"` |
| `start_date` | string | X | 조회 시작일 (`YYYY-MM-DD`) | `"2026-08-11"` |
| `end_date` | string | X | 조회 종료일 (`YYYY-MM-DD`) | `"2026-08-15"` |

- 날짜를 비우면 가장 최근 변경 1건을 반환한다.
- 하루만 지목하면 앞뒤로 `DIFF_DATE_PADDING_DAYS`(기본 1일)만큼 여유를 두고 조회한다.
- 0건이면 `존재하지 않습니다.`, 2건 이상이면 최신 1건 + 전체 건수 안내(`notice`)를 반환한다.
- 응답에 이전 설정 전문(`old`)은 포함되지 않는다 (`new` + `unified_diff`로 복원 가능).

### 사용 예시 (Claude 채팅, config-diff-mcp)

```
최근 paaaa11 서버에 web 변경 내역 알려줘
```

```
8월 11일 was domain PAAA_Domain 설정 변경 내역 알려줘
```

```
paaaa11 http.m 최근에 바뀐 거 있어?
```

### 사용 예시 (Claude 채팅, error-rag-mcp)

```
DB 커넥션 풀 고갈로 응답 지연이 발생했어. 과거에 비슷한 오류가 있었는지 찾아줘.
(오류 코드: ORA-00001)
```

조치를 마친 뒤에는:

```
방금 오류(ORA-00001, DB 커넥션 풀 고갈)에 대해 커넥션 풀 크기를 확장해서 해결했어.
이 내용을 오류/조치 이력으로 등록해줘.
```

---

## 9. 문제 해결

### Python을 찾을 수 없음

```
'python'은(는) 내부 또는 외부 명령, 실행할 수 있는 프로그램, 또는 배치 파일이 아닙니다.
```

→ Python 설치 시 **Add to PATH** 를 체크하지 않은 경우. 환경변수에 수동 추가:

```
시스템 속성 → 환경 변수 → Path → 편집 → 추가:
C:\Users\사용자명\AppData\Local\Programs\Python\Python314\
C:\Users\사용자명\AppData\Local\Programs\Python\Python314\Scripts\
```

### pip install 시 네트워크 에러

```
WARNING: Retrying ... after connection broken
```

→ 오프라인 설치 명령어를 사용한다:

```bash
pip install --no-index --find-links=./offline-packages-win -e .
```

### MCP 서버가 VS Code에서 연결되지 않음

1. `.vscode/mcp.json`의 `command` 경로가 정확한지 확인
2. 가상환경 내 실행파일 존재 여부 확인 (등록한 서버에 해당하는 것만):
   - Windows: `.venv\Scripts\email-mcp.exe`, `.venv\Scripts\extract-error-log-mcp.exe`, `.venv\Scripts\error-rag-mcp.exe`, `.venv\Scripts\config-diff-mcp.exe`
   - Linux: `.venv/bin/email-mcp`, `.venv/bin/extract-error-log-mcp`, `.venv/bin/error-rag-mcp`, `.venv/bin/config-diff-mcp`
3. 터미널에서 직접 실행해 에러 확인:
   ```bash
   .venv\Scripts\email-mcp.exe
   .venv\Scripts\error-rag-mcp.exe
   ```

### SSL 인증서 에러

```
ssl.SSLCertVerificationError: certificate verify failed
```

→ `.env` 파일에서 `API_SSL_VERIFY=false` 로 설정되어 있는지 확인한다.

### 토큰 만료

```
{"msg": "Token has expired"}
```

→ 리발소에서 장기 토큰을 재발급받아 `.env` 파일의 `API_BEARER_TOKEN` 값을 교체한다.

### 이메일 발송 타임아웃

```
httpx.ReadTimeout
```

→ `.env` 파일에 타임아웃 값을 늘린다:

```env
API_TIMEOUT=120
```

---

## 디렉토리 구조 참고

```
email-mcp-server/
├── .env                    ← 환경변수 (git 추적 안 함, API_* 와 RAG_* 모두 여기 작성)
├── .env.example            ← 환경변수 템플릿
├── .vscode/
│   └── mcp.json            ← VS Code MCP 서버 설정
├── pyproject.toml           ← 프로젝트 메타데이터·의존성 (email-mcp/extract-error-log-mcp/error-rag-mcp/config-diff-mcp 엔트리포인트)
├── src/
│   ├── email_mcp/
│   │   ├── __init__.py
│   │   ├── config.py        ← 설정 관리
│   │   ├── client.py        ← EmailApi HTTP 클라이언트
│   │   └── server.py        ← MCP 서버 엔트리포인트
│   ├── extract_error_log_mcp/
│   │   └── ... (config.py / client.py / server.py)
│   ├── error_rag_mcp/
│   │   ├── config.py        ← Settings, 도메인 상수 (MAX_ERROR_SUMMARY_LENGTH 등)
│   │   ├── client.py        ← llm-agent RAG API 클라이언트 (RagClient)
│   │   └── server.py        ← search_similar_error / register_error_resolution 엔트리포인트
│   └── config_diff_mcp/
│       ├── config.py        ← Settings, ResourceSpec(WAS/WEB), 경로·형식·메시지 상수
│       ├── client.py        ← 변경 이력 API 클라이언트 (DiffClient)
│       └── server.py        ← get_diff_was / get_diff_web 엔트리포인트
├── tests/                   ← 서버별 테스트 코드
├── scripts/
│   └── send_test_email.py   ← 발송 테스트 스크립트
├── docs/                    ← 문서
└── offline-packages-win/    ← 오프라인 설치용 Windows wheel 파일 (선택)
```
