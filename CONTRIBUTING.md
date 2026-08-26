# Contributing to Re:Call

Re:Call 프로젝트에 관심 가져주셔서 감사합니다. 버그 제보, 기능 제안, 코드 기여 모두 환영합니다.

<br />

## 이슈 등록

작업을 시작하기 전에 먼저 이슈를 등록해 주세요. 이미 같은 이슈가 있는지 검색 후, 없으면 아래 형식으로 새로 등록합니다.

### 버그 리포트
- 재현 방법 (단계별로)
- 기대했던 동작 vs 실제 동작
- 환경 정보 (OS, 브라우저, 백엔드/프론트엔드 버전 등)
- 가능하다면 로그나 스크린샷 첨부

### 기능 제안
- 해결하려는 문제 또는 필요성
- 제안하는 동작 방식
- (선택) 참고할 만한 유사 사례

<br />

## 개발 환경 세팅

### 1. 저장소 클론
```bash
git clone https://github.com/botato1/AI-Agent-SystemV2.git
cd AI-Agent-SystemV2
```

### 2. 백엔드 세팅 (Python 3.12)
```bash
# PostgreSQL 준비 (macOS)
brew install postgresql@16
brew services start postgresql@16
psql postgres -c "CREATE USER recall WITH PASSWORD 'recall' SUPERUSER;"
psql postgres -c "CREATE DATABASE recall OWNER recall;"
psql -U recall -d recall -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# 가상환경 및 패키지 설치
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r backend/backend_requirements.txt

# 환경변수 설정
cp .env.example .env

# 서버 실행
python -m uvicorn backend.main:app --reload --reload-dir backend --host 0.0.0.0 --port 8000
```

> **Windows 사용자**는 [postgresql.org](https://www.postgresql.org/download/windows/)에서 PostgreSQL 16 설치 프로그램을 받아 설치한 뒤, `psql` 셸에서 위와 같은 `CREATE USER` / `CREATE DATABASE` / `CREATE EXTENSION` 명령을 실행하세요.

API 문서: `http://127.0.0.1:8000/docs`

#### `.env` 작성 시 주의

`.env.example`에는 아직 일부 항목이 반영되어 있지 않습니다. 복사한 뒤 아래 값을 직접 채워야 정상 동작합니다.

```bash
# 필수 — 없으면 DB 연결에 실패합니다
DATABASE_URL=postgresql+psycopg2://recall:recall@localhost:5432/recall

# 실시간 음성 인식 서버 (기본값이 개발 서버 주소이므로 로컬에서는 직접 지정)
STT_SERVER_BASE_URL=http://localhost:8002
STT_STREAM_BASE_URL=ws://localhost:8002
```

Docker Compose로 실행할 때는 `DATABASE_URL`의 호스트를 `localhost` 대신 `postgres`로 지정합니다.

### 3. 프론트엔드 세팅
```bash
cd frontend
npm install
npm run dev
```
`http://localhost:5173`

### 4. Docker로 전체 스택 한 번에 실행
```bash
docker compose up -d --build
```

> **최초 실행 전 `docker-compose.yml`을 사용 환경에 맞게 수정해야 합니다.**
> - `volumes`의 `/mnt/nas_2026_spring/...`, `/srv/dobby/...` 경로는 개발 서버 전용입니다. 로컬에서는 상대경로나 named volume으로 변경하세요.
> - `frontend` 서비스의 `VITE_API_URL`을 접속할 백엔드 주소로 변경하세요 (로컬은 `http://localhost:8000`).
> - GPU가 없으면 `fastapi`·`stt`·`document`·`ollama` 네 서비스의 `deploy.resources.reservations.devices` 항목을 모두 제거하세요.

문서 처리(OCR) 서버는 `document` 서비스로 `docker-compose.yml`에 포함되어 있어(`Dockerfile.document`), `docker compose up`으로 다른 서비스와 함께 뜹니다.

### 5. 문서 처리(OCR) 서버 — Docker 없이 로컬에서 직접 실행하는 경우

`Dockerfile.document`가 실제로 하는 것과 동일한 절차입니다. GPU 드라이버·CUDA 버전에 따라 설치 명령이 달라집니다.

**의존성 설치**

```bash
# Windows (CUDA 12.6)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install paddlepaddle==3.0.0
pip install -r requirements.txt

# Linux 서버 (CUDA 12.8 이상 — RTX 5090/Blackwell은 필수)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install paddlepaddle-gpu==2.6.2 -f https://www.paddlepaddle.org.cn/whl/linux/mkl/avx/stable.html
# -i(index-url) 아니라 -f(find-links)여야 합니다 - 86서버(RTX 5090, Python 3.12)에서 실측 확인함
pip install -r requirements.txt
```

`requirements.txt`는 `backend/modules/document/requirements.txt`입니다.

**실행**

```bash
cd backend/modules/document
python server.py
```

`server.py`가 내부적으로 `uvicorn.run("server:app", host="0.0.0.0", port=8003)`을 호출해 8003 포트로 뜹니다.

**확인**

```bash
curl -X POST http://localhost:8003/api/document
```

GPU(CUDA)가 없으면 매우 느려집니다. `torch.cuda.is_available()`이 `True`인지 먼저 확인하는 걸 권장합니다.

<br />

## 브랜치 전략

모든 작업은 `develop`에서 분기한 브랜치에서 진행하고, 완료되면 `develop`으로 PR을 보냅니다. `main`은 배포 가능한 상태만 유지하는 브랜치입니다.

| Branch | 용도 |
| --- | --- |
| `main` | 배포 가능한 최종 브랜치 |
| `develop` | 개발 통합 브랜치 — 모든 기능 브랜치가 여기로 병합됨 |
| `feature/*` | 기능 개발 |
| `fix/*` | 버그 수정 |
| `infra/*` | 인프라·배포 설정 (Docker, DB, GPU 등) |
| `refactor/*` | 동작 변화 없는 구조 개선 |
| `revert/*` | 이전 변경 되돌리기 |
| `chore/*` | 환경설정·기타 잡무 |
| `disable/*` | 기능 비활성화 |
| `cleanup/*` | 불필요한 코드/리소스 정리 |

브랜치명 예시: `feature/ai-chat-source-highlight`, `fix/meeting-ws-reconnect`

작업을 시작하기 전에 `develop`을 머지해 최신 상태로 맞춰주세요.

```bash
git checkout feature/my-branch
git fetch origin
git merge origin/develop
```

다른 사람의 작업 브랜치는 삭제하거나 force push하지 않습니다. 정리가 필요하면 담당자에게 먼저 확인해 주세요.

<br />

## 커밋 컨벤션

`Type: 작업 내용` 형식을 사용합니다. Type은 영문, 작업 내용은 한글로 작성합니다.

| Type | 용도 |
| --- | --- |
| `Feat` | 새 기능 / API / 모듈 / 스키마 추가 |
| `Fix` | 버그 / import / 필드명 수정 |
| `Update` | 기존 기능의 비버그성 개선 |
| `Docs` | 문서(README, 스키마 가이드 등) 수정 |
| `Style` | 동작 변화 없는 포맷팅 |
| `Refactor` | 동작 변화 없는 구조 개선 |
| `Remove` | 파일 / 코드 / 주석 삭제 |
| `Rename` | 파일 / 클래스 / 함수명 변경 |
| `Move` | 파일 / 폴더 이동 |
| `Test` | 테스트 코드 |
| `Chore` | 환경설정 / 빌드 / 의존성 등 기타 작업 |

**하나의 커밋에는 하나의 작업 단위만 담아주세요.** 관련 없는 작업을 한 커밋에 묶거나, 버그 수정과 새 기능을 같은 커밋에 섞지 않습니다.

```bash
Feat: 문서를 회의에 직접 연결하는 기능 추가
Fix: 문서 업로드 파라미터명 불일치 수정
Docs: README 갱신
```

판단이 필요했던 변경은 제목 아래에 **왜 그렇게 했는지**를 함께 남겨주세요. 나중에 코드를 읽는 사람이 근거를 알 수 있습니다.

```
Fix: change_summary_generate가 자체 httpx 호출을 써서 중국어 감지 재시도가
     안 걸리던 문제 수정

기준문서 갱신 결과 팝업에 중국어가 섞여 나오는 문제. contradiction_crud.py와
동일하게 공용 _call_ollama()로 통일해 재시도 로직을 함께 적용받도록 함.
```

<br />

## Pull Request 절차

1. `develop`에서 새 브랜치를 분기합니다.
2. 작업 단위별로 커밋 컨벤션에 맞게 커밋합니다.
3. 작업이 끝나면 `develop`을 대상으로 PR을 엽니다.
4. PR 설명에는 다음을 포함해 주세요:
   - 변경 사항 요약
   - 관련 이슈 번호(있다면)
   - **확인한 내용** — 어떻게 검증했는지 (테스트 결과, 재현 절차, 수정 전후 비교 등)
   - 영향 범위 — 어떤 기능에 영향이 가는지, API 스펙 변경이 있는지
5. 리뷰 후 승인되면 `develop`에 병합됩니다.

같은 이름의 브랜치 접두사(`feature/`)를 통일해서 사용해 주세요 — `feat/`와 `feature/`가 혼용되지 않도록 부탁드립니다.

### PR을 올리기 전에

- [ ] `develop`을 머지해 충돌을 해결했습니다
- [ ] 변경한 부분과 관련된 테스트가 통과합니다
- [ ] 이 PR과 무관한 파일이 diff에 섞여 있지 않습니다
- [ ] 디버깅용 `print`나 주석 처리한 코드를 정리했습니다

<br />

## 코드 리뷰

### 리뷰어에게

- **PR 설명만 보지 말고 코드를 직접 확인해 주세요.** 설명과 실제 구현이 다른 경우가 있습니다.
- 문제를 발견하면 **재현 방법이나 근거를 함께 남겨주세요.** "이럴 것 같다"보다 "이렇게 하면 이 에러가 난다"가 훨씬 도움이 됩니다.
- 병합을 막아야 하는 문제와 단순 제안을 구분해서 표시해 주세요.

### 작성자에게

- 리뷰 지적을 반영했으면 **코드 주석에 근거를 남겨주세요.** 나중에 "왜 이렇게 되어 있지?"를 다시 묻지 않게 됩니다.

  ```python
  # [수정 - 리뷰 반영] 독자적으로 OLLAMA_MODEL/httpx를 재선언해서 호출하던 것을
  # 공용 _call_ollama()로 통일 - 중국어 출력 재시도 로직을 함께 적용받기 위함
  ```

- 지적에 동의하지 않으면 그냥 반영하지 말고, 근거를 들어 논의해 주세요.

<br />

## 테스트

테스트는 `pytest` 규약을 따르며, 테스트 대상 모듈과 같은 디렉터리에 `test_*.py`로 둡니다.

```bash
pip install pytest

pytest                                    # 전체 실행
pytest backend/modules/post_meeting/      # 특정 디렉터리만
pytest -k reading_order                   # 이름으로 필터
```

### 테스트를 추가해야 하는 경우

- **버그를 고쳤을 때** — 그 버그를 재현하는 회귀 테스트를 함께 추가합니다. 같은 문제가 다시 생기는 것을 막습니다.
- **판단 로직·파싱 로직을 건드렸을 때** — 입력에 따라 결과가 갈리는 코드는 경계 조건을 테스트로 고정합니다.

### 참고할 만한 예시

- `backend/modules/document/doc_processor/postprocess/test_reading_order_regression.py` — 실제 버그 사례를 재현하는 회귀 테스트
- `backend/modules/post_meeting/test_decision_transition.py` — 외부 의존성을 가짜 객체로 대체한 단위 테스트

### 정확도 측정

OCR처럼 정확도가 중요한 기능은 측정 스크립트와 근거 문서를 함께 남깁니다.

- 측정 스크립트: `backend/modules/document/eval_ocr_accuracy.py`
- 측정 근거: `docs/ocr_accuracy_evidence.md`

수치를 주장할 때는 **어떤 표본으로 어떻게 측정했는지**를 함께 기록해 주세요.

<br />

## 코드 스타일

- 백엔드: Python (PEP 8 준수 권장), FastAPI 라우터/서비스/CRUD 계층 구조를 따릅니다.
- 프론트엔드: TypeScript, React, 기존 컴포넌트 구조(`components/`, `pages/`)를 따릅니다.
- 새로운 의존성을 추가할 때는 라이선스가 OSI 인증 라이선스(MIT, Apache-2.0 등)인지 확인해 주세요.
- 판단이 필요했던 코드에는 이유를 주석으로 남깁니다. 무엇을 하는지는 코드가 말해주지만, 왜 그렇게 했는지는 주석만이 말해줍니다.

### LLM 호출은 공용 클라이언트를 사용합니다

개별 파일에서 `httpx`로 Ollama를 직접 호출하지 마세요.

```python
from backend.modules.llm.ollama_client import _call_ollama, OLLAMA_MODEL_LIGHT

result = _call_ollama(prompt, model=OLLAMA_MODEL_LIGHT, temperature=0)
```

공용 함수에는 한국어 외 언어 출력 감지 시 재시도, `keep_alive` 설정 등이 이미 들어 있습니다. 직접 호출하면 이런 처리를 놓치게 됩니다.

### 프론트엔드 빌드 확인

PR을 올리기 전에 빌드가 통과하는지 확인해 주세요.

```bash
cd frontend && npm run build
```

<br />

## 라이선스

이 프로젝트에 기여하는 코드는 [MIT License](./LICENSE) 하에 배포됩니다. PR을 제출하는 것은 이 라이선스에 동의하는 것으로 간주됩니다.
