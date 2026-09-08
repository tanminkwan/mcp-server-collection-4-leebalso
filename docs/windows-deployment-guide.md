# Windows 오프라인 배포 가이드 (소스 코드 미포함)

본 가이드는 소스 코드를 대상 서버에 가져가지 않고, 깔끔하게 빌드된 결과물(`.whl`)만으로 오프라인 Windows 환경에 MCP 서버를 배포하고 설치하는 정석적인 방법을 설명합니다.

## 1. 배포 준비 (인터넷 연결 환경)

### 1-1. 프로젝트 빌드 (.whl 파일 생성)
프로젝트 자체를 운영체제에 구애받지 않는 파이썬 패키지(Wheel)로 빌드합니다.
명령어는 반드시 `pyproject.toml`이 있는 **프로젝트 최상위 폴더(예: `mcp-server/`)**에서 가상환경을 켠 상태로 실행해야 합니다.
```bash
# 가상환경 활성화 (Linux 기준)
source .venv/bin/activate

# 빌드 도구가 없다면 설치: pip install build
python -m build
```
빌드가 완료되면 프로젝트 내 `dist/` 폴더 아래에 `mcp_server_collection-0.1.0-py3-none-any.whl` (버전에 따라 다름) 파일이 생성됩니다.

### 1-2. Windows 타겟 오프라인 패키지 구성
Windows 64bit 환경에서 구동될 수 있도록 외부 의존성 라이브러리 파일들을 다운로드합니다.
현재 OS가 Linux이더라도, 아래 명령어를 통해 Windows용(`.whl`) 파일을 지정해서 받을 수 있습니다.

```bash
pip download --platform win_amd64 --python-version 3.14 --only-binary=:all: -d ./offline-packages-win .
```
명령어가 성공하면 `offline-packages-win/` 디렉토리에 Windows 타겟 OS용 `.whl` 파일들이 저장됩니다.

### 1-3. 전송할 파일 정리
이제 보안상 노출될 필요가 없는 소스 코드(`src/` 등)는 제외하고, 아래 항목들만 USB나 망연계 시스템을 통해 대상 Windows PC로 전송합니다.
1. `dist/mcp_server_collection-0.1.0-py3-none-any.whl` (방금 빌드한 MCP 서버 모음 본체 파일)
2. `offline-packages-win/` 폴더 통째로 (의존성 라이브러리 묶음)
3. Windows용 파이썬 오프라인 설치 파일 (예: `python-3.14.x-amd64.exe` - 윈도우 환경에 파이썬이 없는 경우)

---

## 2. Windows PC에서 설치 (오프라인 타겟 환경)

### 2-1. 파이썬 설치
1. 가져간 파이썬 설치 파일(`python-3.14.x-amd64.exe`)을 실행합니다.
2. 첫 설치 화면에서 **`☑ Add python.exe to PATH`**를 반드시 체크한 후 설치를 완료합니다.

### 2-2. 작업 폴더 구성 및 가상환경 생성
적당한 배포 폴더(예: `C:\mcp-server`)를 만들고, 가져온 **`.whl` 파일과 `offline-packages-win` 폴더**를 이 곳에 위치시킵니다.
이후 명령 프롬프트(cmd)나 PowerShell을 열어 가상환경(`.venv`)을 구성합니다.

```powershell
cd C:\mcp-server
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2-3. 오프라인 설치
활성화된 가상환경 내에서 아래 명령어를 실행하여 MCP 서버를 설치합니다.

```powershell
# mcp_server_collection 파일명은 실제 생성된 버전에 맞게 수정하여 입력합니다.
# 이미 동일한 버전이 설치되어 있어도 덮어쓰도록 --force-reinstall 옵션을 사용합니다.
pip install mcp_server_collection-0.1.0-py3-none-any.whl --no-index --find-links=./offline-packages-win --force-reinstall
```
이 과정에서 소스 코드를 참조하지 않고(`.whl` 파일 기반), 오프라인 패키지 폴더에서 필요한 라이브러리를 모두 가져와 설치가 완료됩니다.

### 2-4. 설치 검증 및 실행 (.exe 자동 생성 확인)
설치가 정상적으로 완료되면, 가상환경의 `Scripts` 폴더 내에 MCP 서버 실행을 위한 `.exe` 래퍼(Wrapper) 파일들이 **자동으로 생성**됩니다. (Windows에서 빌드하지 않아도 됩니다.)

```powershell
# 설치된 MCP 서버가 오류 없이 실행되는지 확인
# (실행 시 프롬프트가 멈춘 것처럼 대기 상태가 되면 정상입니다. stdio 통신을 기다리는 상태입니다.)
# 확인 후 Ctrl+C 로 종료하세요.
.venv\Scripts\email-mcp.exe
.venv\Scripts\extract-error-log-mcp.exe
.venv\Scripts\error-rag-mcp.exe
.venv\Scripts\config-diff-mcp.exe
```
실행했을 때 `ModuleNotFoundError` 같은 에러 없이 무한 대기 상태로 진입한다면 완벽하게 설치된 것입니다.

---

## 3. 환경 변수 설정 및 구동 (.env)

설치된 MCP 서버를 실제로 구동하기 위해 필요한 환경변수 설정입니다.
실행 디렉토리(`C:\mcp-server`)에 `.env` 파일을 만들고 아래와 같이 설정합니다.

```env
# email-mcp / extract-error-log-mcp / config-diff-mcp 공유 설정
API_BASE_URL=https://app.mwm.local:20443
API_BEARER_TOKEN=발급받은_JWT_토큰_입력
API_SSL_VERIFY=false
# 선택: 수신자 이름 매핑 (JSON 또는 이름:이메일 콤마 구분)
EMAIL_RECIPIENT_MAPPING=홍길동:hong@example.com, 김철수:kim@example.com

# error-rag-mcp 전용 설정 (llm-agent RAG API, 위 API_* 와는 별도)
RAG_API_BASE_URL=http://localhost:28000
# 선택: 현재 llm-agent는 API Key 없이 접근 가능. 인증이 필요해지면 설정.
RAG_API_BEARER_TOKEN=
RAG_API_SSL_VERIFY=false
RAG_COLLECTION_NAME=여기에_실제_콜렉션_ID_입력
RAG_DOMAIN_ID=여기에_실제_도메인_ID_입력

# config-diff-mcp 전용 설정 (접속 정보는 위 API_* 를 공유)
# 선택: 단일 일자만 지정됐을 때 앞뒤로 확장할 일수 (기본 1일)
DIFF_DATE_PADDING_DAYS=1
```

*참고: `EMAIL_RECIPIENT_MAPPING`을 설정하면 이메일 주소 대신 `홍길동` 같은 수신자 이름만 전달해도 자동으로 이메일 주소로 변환하여 발송합니다.*

이제 VS Code의 `mcp.json`이나 클라이언트 설정 파일에서 `command` 경로를 서버별로 지정하여 사용하시면 됩니다
(예: `C:\mcp-server\.venv\Scripts\email-mcp.exe`, `C:\mcp-server\.venv\Scripts\error-rag-mcp.exe`,
`C:\mcp-server\.venv\Scripts\config-diff-mcp.exe`)!


---

## 4. [대안] 소스 코드를 가져가서 오프라인 Windows 환경에서 직접 빌드하는 방법

보안상 소스 코드를 반출하는 것이 문제가 되지 않아서, 소스 코드를 통째로 Windows 환경으로 가져간 뒤 윈도우에서 직접 `.whl` 파일을 구워내고 싶다면 아래 절차를 따릅니다.

### 4-1. 빌드 도구 오프라인 패키지 준비 (Linux 등 인터넷 연결 환경)
파이썬의 패키지 빌드 도구들은 순수 파이썬 라이브러리(Pure Python)이므로 OS에 종속되지 않습니다.
프로젝트 최상위에서 `tmp` 폴더를 만들고 빌드용 패키지를 다운로드합니다.

```bash
mkdir -p tmp
pip download -d ./tmp build setuptools wheel
```
이제 소스 코드 전체와 `tmp` 폴더, 그리고 `offline-packages-win` 폴더를 모두 Windows로 가져갑니다.

### 4-2. Windows에서 오프라인으로 빌드하기
Windows 가상환경(`.venv`)을 켠 상태에서, 가져온 `tmp` 폴더를 이용해 빌드 도구들을 먼저 오프라인 설치합니다.

```powershell
# 1. 빌드 도구 오프라인 설치
pip install --no-index --find-links=./tmp build setuptools wheel

# 2. 오프라인 휠(.whl) 빌드 (--no-isolation 필수)
python -m build --no-isolation
```

**⚠️ `--no-isolation` 옵션을 사용하는 이유:**
원래 `python -m build`를 실행하면 인터넷에서 임시 환경(Isolation) 구축을 위한 라이브러리들을 자동으로 다운받으려고 시도합니다. 인터넷이 차단된 오프라인 환경에서는 이 과정에서 에러가 발생하므로, `--no-isolation` 옵션을 주어 "미리 설치해둔(tmp에서 가져온) 도구들을 그대로 사용하여 임시 환경 없이 빌드하라"고 강제하는 것입니다.

빌드가 끝나면 `dist/` 폴더에 `.whl` 파일이 생성되며, 이후 설치는 본 문서의 `2-3. 오프라인 설치` 단계와 동일하게 진행하시면 됩니다.

---

## 5. 소스 코드 수정 후 오프라인 재배포 (업데이트) 방법

인터넷이 단절된 Windows 환경에서 코드를 직접 수정(`src/` 하위 파일 등)하고 이를 다시 적용하려면 아래 과정을 거쳐 업데이트합니다.

1. **가상환경 활성화**
   ```powershell
   cd C:\mcp-server
   .venv\Scripts\Activate.ps1
   ```

2. **이전 빌드 산출물 삭제 (권장)**
   새로운 빌드 파일과 혼동되지 않도록 기존 휠 파일을 지웁니다.
   ```powershell
   Remove-Item -Path .\dist\* -Recurse -Force
   ```

3. **오프라인 재빌드**
   수정된 코드를 바탕으로 새로운 휠(`.whl`) 파일을 빌드합니다. 인터넷이 없으므로 반드시 `--no-isolation` 옵션을 사용해야 합니다.
   *(※ 4-2 단계의 빌드 도구가 이미 설치되어 있어야 합니다.)*
   ```powershell
   python -m build --no-isolation
   ```

4. **강제 재설치 (업데이트 적용)**
   새로 빌드된 패키지를 `--force-reinstall` 옵션으로 덮어씌웁니다. 외부 라이브러리 참조를 위해 기존 `offline-packages-win` 폴더도 함께 지정합니다.
   ```powershell
   # 실제 dist 폴더에 생성된 버전에 맞게 파일명 수정
   pip install .\dist\mcp_server_collection-0.1.0-py3-none-any.whl --no-index --find-links=.\offline-packages-win --force-reinstall
   ```
