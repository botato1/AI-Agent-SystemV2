# Re:Call (AI-Agent-System)

> 회의록, 문서, 음성 데이터를 AI Agent가 분석해 업무 정보를 자동으로 정리하고, 발언과 결정사항의 모순을 실시간으로 감지하는 팀 협업 플랫폼

<br />

## Service Overview

Re:Call은 회의록, 문서, 음성 파일 등 업무 과정에서 발생하는 비정형 데이터를 AI Agent가 분석하여 핵심 내용을 요약하고, 할 일을 추출하며, RAG 기반 질의응답을 제공하는 업무 자동화 플랫폼입니다.

회의가 진행되는 동안 발화 내용이 과거 결정사항이나 참고 문서와 모순되면 실시간으로 감지해 알려주고, 회의가 끝나면 요약·결정사항·할 일을 자동으로 정리합니다. 사용자는 문서나 음성 파일을 업로드하거나 채팅으로 질문할 수 있으며, 시스템은 업로드된 자료와 회의 기록을 바탕으로 답변을 생성합니다.

이를 통해 반복적인 문서 확인 작업과 "말 바뀜"으로 인한 혼선을 줄이고, 흩어진 업무 정보를 하나의 지식 자산으로 관리하는 것을 목표로 합니다.

<br />

## Key Features

| 기능 | 설명 |
| --- | --- |
| 실시간 변경 감지 | 회의 발화/채팅 메시지가 과거 결정사항과 충돌하면 즉시 감지해 근거와 함께 알립니다. (업로드 문서 대비 감지는 구현은 되어 있으나 현재 비활성화 상태이며, 코드/설정값 대비 감지는 스키마만 준비된 향후 계획입니다) |
| 회의 요약 & 후처리 | 회의 종료 후 전체 요약, 핵심 요약, 논의사항, 결정사항, 할 일을 자동으로 추출합니다. |
| AI Chat (RAG) | 회의록/문서/결정사항을 대상으로 하이브리드 검색(의미+키워드) 및 리랭킹 기반으로 질문에 답변합니다. |
| 실시간 STT | 회의 음성을 실시간으로 텍스트 변환하고 화자를 분리합니다. |
| 각자 PC / 한 대의 PC 모드 | 참가자별 개별 접속(원격 회의)과 한 기기 공용 진행(오프라인 회의)을 모두 지원하며, 참가자 간 음성 통화 중계를 제공합니다. |
| 문서 분석 & OCR | PDF, 이미지, DOCX 등 업로드 문서의 레이아웃을 분석하고 텍스트/표/차트를 추출합니다. |
| 회의 자료 연결 | 회의별로 참고 문서를 직접 첨부·조회·삭제할 수 있습니다. |
| 워크스페이스 관리 | 팀/프로젝트 단위로 회의·문서·결정사항을 격리해서 관리합니다. |

<br />

## Architecture

```text
User
  │
  ├── 회의 참여 (음성 스트리밍)
  ├── 채팅 / AI Chat 질문
  └── 문서 업로드
        │
        ▼
FastAPI Backend
  ├── Meeting / Meeting WS Router  — 실시간 회의 세션, STT 중계
  ├── Document Router              — 문서 업로드/조회
  ├── Contradiction Router         — 모순 조회/수정/해결
  ├── AI Chat Router               — RAG 질의응답
  └── Workspace / Auth / Task / Notification Router
        │
        ├── STT 서버      (실시간 음성 인식 + 화자 분리)
        └── 문서 처리 서버 (레이아웃 분석 / OCR / VL 추출, GPU 서버 분리)
        │
        ▼
LangGraph Pipelines
  ├── contradiction_graph        — 실시간 변경 판단 (발화 vs 과거 결정사항)
  ├── meeting_postprocess_graph  — 회의 종료 후 요약/결정사항/할 일 추출
  ├── ai_chat_graph              — RAG 검색 + 답변 생성
  └── change_summary_graph       — 모순 "변경 인지함" 처리 후 요약 초안 생성
        │
        ▼
PostgreSQL (관계형 데이터)  ──  ChromaDB (임베딩 / RAG 검색)  ──  Ollama (LLM 추론)
```

두 대의 서버에 Docker Compose로 분산 배포되어 있습니다.
- **Server 1** — FastAPI 백엔드, PostgreSQL, 프론트엔드(nginx), Ollama, STT 서버 (NVIDIA GB10)
- **Server 2** — 문서 처리(OCR/VL) 서버, GPU 리소스 격리 (NVIDIA RTX 5090)

<br />

## Tech Stack

### Backend

| Category | Stack |
| --- | --- |
| Language | Python |
| Framework | FastAPI |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy |
| Schema Validation | Pydantic |
| Auth | JWT (access / refresh 이원화) |

### AI / Agent

| Category | Stack |
| --- | --- |
| Agent Workflow | LangGraph  |
| LLM | Ollama |
| Vector Database | ChromaDB |
| Search | 하이브리드 검색 (bge-m3 의미 검색 + BM25 키워드 검색) |
| Reranking | bge-reranker-v2-m3 |

### Document Processing

| Category | Stack |
| --- | --- |
| Layout Analysis | YOLO 기반 커스텀 레이아웃 분류기 |
| Text / Table Extraction | PyMuPDF, pdfplumber |
| OCR (표) | PaddleOCR-VL |
| Chart / Diagram 이해 | Qwen3-VL |
| Fallback | Gemini API |

### Voice Processing

| Category | Stack |
| --- | --- |
| STT (확정 전사) | Qwen3-ASR-1.7B |
| STT (실시간 잠정 전사) | Qwen3-ASR-0.6B |
| Speaker Diarization | pyannote/speaker-diarization-3.1 |
| Speaker Embedding | pyannote/wespeaker-voxceleb-resnet34-LM |
| VAD | Silero VAD |
| Overlap Detection | pyannote/segmentation-3.0 |

### Frontend

| Category | Stack |
| --- | --- |
| Language | TypeScript |
| Framework | React |
| Build Tool | Vite |
| Styling | Tailwind CSS |

<br />

## Document Processing Pipeline

문서 처리 서버는 업로드된 PDF 또는 이미지 문서에서 레이아웃, 텍스트, 표, 차트 정보를 추출하여 RAG 검색에 활용 가능한 형태로 변환합니다.

| 처리 영역 | 사용 기술 | 설명 |
| --- | --- | --- |
| Layout | YOLO 분류기 | 문서의 레이아웃 구조(제목/본문/표/이미지 등)를 분석합니다. |
| Text | PyMuPDF | PDF 내부 텍스트를 추출합니다. |
| Table | pdfplumber, PaddleOCR-VL | 텍스트 기반 표와 이미지 기반 표를 각각 추출합니다. |
| Chart / Diagram | Qwen3-VL | 차트/다이어그램/인포그래픽 내용을 해석합니다. |
| Fallback | Gemini API | 위 엔진이 실패하거나 신뢰도가 낮을 때 보조로 사용합니다. |
| Postprocess | 자체 로직 | 자간/줄바꿈/세로쓰기/표 정리 등 텍스트 후처리를 거쳐 RAG용 청크로 변환합니다. |

<br />

## API Flow

### Meeting Flow (실시간 회의)

```text
POST /api/workspaces/{workspace_id}/meetings/start
  (또는 예약된 회의는 POST .../meetings/{meeting_id}/begin)
  ↓
WS /api/workspaces/{workspace_id}/meetings/{meeting_id}/stream
  ↓
STT 서버로 오디오 스트리밍 중계
  ↓
실시간 자막(partial/final) 프론트로 릴레이
  ↓
발화 세그먼트 저장
  ↓
contradiction_graph 실행 — 과거 결정사항과 비교
  ↓
모순 감지 시 실시간 알림
  ↓
(회의 종료) meeting_postprocess_graph 실행
  ↓
요약 / 결정사항 / 할 일 추출 → DB 저장 + RAG 인덱싱
```

### Document Flow

```text
POST /api/workspaces/{workspace_id}/documents/upload
  ↓
문서 처리 서버로 전달
  ↓
레이아웃 분석 → 텍스트 / 표 / 차트 추출 → 후처리
  ↓
청킹 및 임베딩
  ↓
ChromaDB에 컬렉션별 저장 (문서 / 회의 / 결정)
  ↓
RAG 검색 및 모순 감지 참조 자료로 활용
```

### AI Chat Flow

```text
POST /api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat/sessions/{session_id}/messages
  ↓
ai_chat_graph 실행
  ↓
하이브리드 검색 (의미 + BM25) → 컬렉션별 후보 수집
  ↓
리랭킹 (bge-reranker-v2-m3)
  ↓
LLM 답변 생성 + 근거자료(source) 반환
```

### Contradiction Flow

```text
실시간 모순 감지 → contradictions 테이블 저장
  ↓
PATCH /api/workspaces/{workspace_id}/contradictions/{id} — 감지 내용 수정
  ↓
POST .../{id}/resolve 또는 /dismiss — 처리(변경 인지함 / 기준 유지 / 닫기)
  ↓
(변경 인지함 시) change_summary_graph 실행 → 변경 요약 초안 생성
```

<br />

## Main APIs

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/auth/signup` `/login` | 회원가입 / 로그인 |
| POST | `/api/auth/password-reset/request` `/confirm` | 비밀번호 재설정 |
| POST | `/api/workspaces/{workspace_id}/meetings/start` | 즉석 회의 생성 및 시작 |
| POST | `/api/workspaces/{workspace_id}/meetings/{meeting_id}/begin` | 예약된(scheduled) 회의를 실제 녹음으로 전환 |
| POST | `/api/workspaces/{workspace_id}/meetings/{meeting_id}/end` | 회의 종료 |
| WS | `/api/workspaces/{workspace_id}/meetings/{meeting_id}/stream` | 실시간 회의 스트리밍 (STT 중계, 모순 알림) |
| POST | `/api/workspaces/{workspace_id}/meetings/{meeting_id}/segments/{segment_id}/split` | 발화 세그먼트 분할 |
| GET | `/api/workspaces/{workspace_id}/meetings/{meeting_id}/documents` | 회의 첨부 문서 조회 |
| POST | `/api/workspaces/{workspace_id}/documents/upload` | 문서 업로드 및 분석 |
| GET | `/api/workspaces/{workspace_id}/contradictions/{id}` | 모순 상세 조회 |
| PATCH | `/api/workspaces/{workspace_id}/contradictions/{id}` | 모순 감지 내용 수정 |
| POST | `/api/workspaces/{workspace_id}/contradictions/{id}/resolve` | 모순 해결 처리 |
| POST | `/api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat/sessions/{session_id}/messages` | AI Chat 질의 |
| POST | `/api/stt/schedule` | STT 처리 예약/실행 |

<br />

## Graph & State

Re:Call은 목적별로 분리된 여러 LangGraph 파이프라인으로 구성되어 있으며, 각 그래프는 자체 State를 갖습니다.

| Graph | 실행 시점 | 주요 State 필드 |
| --- | --- | --- |
| `contradiction_graph` | 회의 발화 / 채팅 메시지 저장 직후 | `statement`, `candidates`(RAG 후보), `judgment_case`, `contradiction` |
| `meeting_postprocess_graph` | 회의 종료(`/end`) 시 | `transcript`, `extracted_decisions`, `extracted_tasks`, `full_summary`, `short_summary` |
| `ai_chat_graph` | AI Chat 메시지 전송 시 | `question`, `search_results`, `reranked_results`, `final_answer`, `sources` |
| `change_summary_graph` | 모순 "변경 인지함" 처리 시 | `original_reference_text`, `accepted_change_text`, `generated_summary` |

<br />

## Folder Structure

```text
AI-Agent-SystemV2/
├── backend/
│   ├── main.py
│   ├── core/                 # 보안(JWT), 설정
│   ├── routers/
│   │   ├── auth_router.py
│   │   ├── workspace_router.py
│   │   ├── category_router.py
│   │   ├── meeting_router.py
│   │   ├── meeting_ws_router.py
│   │   ├── document_router.py
│   │   ├── document_ws_router.py
│   │   ├── contradiction_router.py
│   │   ├── ai_chat_router.py
│   │   ├── rag_router.py
│   │   ├── chat_router.py
│   │   ├── room_ws_router.py
│   │   ├── task_router.py
│   │   ├── stt_router.py
│   │   ├── worktree_router.py
│   │   ├── notification_router.py
│   │   ├── dashboard_router.py
│   │   └── webhook_router.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── meeting_service.py
│   │   ├── meeting_reminder_service.py
│   │   ├── document_service.py
│   │   ├── judgment_service.py
│   │   ├── rag_service.py
│   │   ├── similarity_service.py
│   │   ├── chat_service.py
│   │   ├── ollama_service.py
│   │   ├── stt_stream_client.py
│   │   └── stt_upload_service.py
│   ├── graphs/
│   │   ├── contradiction_graph.py
│   │   ├── meeting_postprocess_graph.py
│   │   ├── ai_chat_graph.py
│   │   ├── change_summary_graph.py
│   │   ├── nodes/
│   │   └── states/
│   ├── schemas/               # Pydantic 스키마 (도메인별 *_schema.py)
│   ├── db/
│   │   ├── modules/           # SQLAlchemy 모델
│   │   └── crud/              # CRUD 함수
│   └── modules/
│       ├── document/          # 문서 처리(OCR/VL) 서버 — doc_processor/
│       ├── stt/                # STT 서버 (Qwen3-ASR + pyannote)
│       ├── rag/                # ChromaDB 클라이언트, 검색/리랭킹
│       ├── judgment/           # 실시간 모순 판단 로직
│       ├── post_meeting/       # 회의 후처리(요약/결정/할일 추출) 로직
│       └── llm/                # Ollama 클라이언트
│
├── frontend/
│   └── src/
│       ├── components/
│       ├── hooks/
│       ├── services/
│       ├── lib/
│       ├── data/
│       ├── utils/
│       ├── App.tsx
│       └── main.tsx
│
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

<br />

## Getting Started

### 1. Repository Clone

```bash
git clone https://github.com/botato1/AI-Agent-SystemV2.git
cd AI-Agent-SystemV2
```

<br />

## Backend 실행 방법

### 1. PostgreSQL 준비

```bash
brew install postgresql@16
brew services start postgresql@16
psql postgres -c "CREATE USER recall WITH PASSWORD 'recall' SUPERUSER;"
psql postgres -c "CREATE DATABASE recall OWNER recall;"
psql -U recall -d recall -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

### 2. 가상환경 생성 및 활성화

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

### 3. 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. 환경변수 설정

`.env.example`을 참고해 `.env` 파일을 생성합니다. (DB 연결 정보는 `DATABASE_URL`로 오버라이드 가능, 기본값은 `postgresql+psycopg2://recall:recall@localhost:5432/recall`)

```bash
cp .env.example .env
```

### 5. 로컬 개발 서버 실행

```bash
python -m uvicorn backend.main:app --reload --reload-dir backend --host 0.0.0.0 --port 8000
```

```text
http://127.0.0.1:8000/docs
```

<br />

## Frontend 실행 방법

```bash
cd frontend
npm install
npm run dev
```

```text
http://localhost:5173
```

<br />

## Docker로 전체 스택 실행

```bash
docker compose up -d
```

<br />

## Contributors

| Name | Role |
| --- | --- |
| 가동현 | Team Lead, LangGraph 노드 로직, 인프라(docker-compose) |
| 문지수 | Backend (routers / services / crud / schemas) |
| 이승주 | 모순 판단(judgment), RAG(chroma_client), 회의 후처리(post_meeting) |
| 이준오 | STT 서버 |
| 정승현 | 문서/OCR 처리 서버 |
| 김나연 | 프론트엔드, 문서/OCR 처리 서버 |

<br />

## Branch Convention

| Branch | Description |
| --- | --- |
| `main` | 배포 가능한 최종 브랜치 |
| `develop` | 개발 통합 브랜치 |
| `feature/*` | 기능 개발 브랜치 |
| `fix/*` | 버그 수정 브랜치 |
| `infra/*` | 인프라·배포 설정 브랜치 (Docker, DB, GPU 등) |
| `refactor/*` | 동작 변화 없는 구조 개선 브랜치 |
| `revert/*` | 이전 변경 되돌리기 브랜치 |
| `chore/*` | 환경설정·기타 잡무 브랜치 |
| `disable/*` | 기능 비활성화 브랜치 |
| `cleanup/*` | 불필요한 코드/리소스 정리 브랜치 |

<br />

## Commit Convention

`Type: 작업 내용` 형식을 사용합니다. Type은 영문, 작업 내용은 한글로 작성합니다.

| Type | Use |
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

하나의 커밋에는 하나의 작업 단위만 담습니다 (예: 스키마 파일 하나 추가, 라우터 하나 추가, import 오류 하나 수정). 관련 없는 작업을 한 커밋에 묶거나, 버그 수정과 새 기능을 같은 커밋에 섞지 않습니다.

예시:

```bash
Feat: 문서를 회의에 직접 연결하는 기능 추가
Fix: 문서 업로드 파라미터명 불일치 수정
Docs: README 갱신
```

<br />

## Expected Effect

- 회의록, 문서, 음성 자료를 자동으로 정리할 수 있습니다.
- 발언이 과거 결정사항과 모순되는 상황을 실시간으로 인지해 혼선을 줄일 수 있습니다.
- 회의나 문서에서 나온 할 일을 자동으로 추출할 수 있습니다.
- 업로드된 문서와 회의 기록을 기반으로 질문하고 답변받을 수 있습니다.
- 원격/오프라인 회의 모두에서 동일한 수준으로 회의 정보를 기록하고 활용할 수 있습니다.

<br />

## Future Improvements

- 사용자별 문서 권한 관리
- AI Chat 검색 임계값(threshold) 튜닝 — 재현율/정밀도 균형 개선
- 문서 업로드 시 회의자료(meeting_reference)와 결정 근거 자료 분리 고도화
- 일정 추출 및 캘린더 연동
- Agent 실행 흐름 시각화
- Alembic 도입을 통한 스키마 마이그레이션 관리
- 서버 이관 및 배포 환경 고도화

<br />

## License

This project is licensed under the MIT License — see the [LICENSE](./LICENSE) file for details.
