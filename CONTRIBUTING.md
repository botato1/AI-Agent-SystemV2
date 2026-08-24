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

### 2. 백엔드 세팅
```bash
# PostgreSQL 준비
brew install postgresql@16
brew services start postgresql@16
psql postgres -c "CREATE USER recall WITH PASSWORD 'recall' SUPERUSER;"
psql postgres -c "CREATE DATABASE recall OWNER recall;"
psql -U recall -d recall -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# 가상환경 및 패키지 설치
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env

# 서버 실행
python -m uvicorn backend.main:app --reload --reload-dir backend --host 0.0.0.0 --port 8000
```
API 문서: `http://127.0.0.1:8000/docs`

### 3. 프론트엔드 세팅
```bash
cd frontend
npm install
npm run dev
```
`http://localhost:5173`

### 4. Docker로 전체 스택 한 번에 실행
```bash
docker compose up -d
```

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

<br />

## Pull Request 절차

1. `develop`에서 새 브랜치를 분기합니다.
2. 작업 단위별로 커밋 컨벤션에 맞게 커밋합니다.
3. 작업이 끝나면 `develop`을 대상으로 PR을 엽니다.
4. PR 설명에는 다음을 포함해 주세요:
   - 변경 사항 요약
   - 관련 이슈 번호(있다면)
   - 테스트 방법 또는 확인한 내용
5. 리뷰 후 승인되면 `develop`에 병합됩니다.

같은 이름의 브랜치 접두사(`feature/`)를 통일해서 사용해 주세요 — `feat/`와 `feature/`가 혼용되지 않도록 부탁드립니다.

<br />

## 코드 스타일

- 백엔드: Python (PEP 8 준수 권장), FastAPI 라우터/서비스/CRUD 계층 구조를 따릅니다.
- 프론트엔드: TypeScript, React, 기존 컴포넌트 구조(`components/`, `pages/`)를 따릅니다.
- 새로운 의존성을 추가할 때는 라이선스가 OSI 인증 라이선스(MIT, Apache-2.0 등)인지 확인해 주세요.

<br />

## 라이선스

이 프로젝트에 기여하는 코드는 [MIT License](./LICENSE) 하에 배포됩니다. PR을 제출하는 것은 이 라이선스에 동의하는 것으로 간주됩니다.