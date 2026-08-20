# 모순 해결 변경요약 생성 노드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ChangeSummaryDraft`(모순을 "변경 인지함"으로 처리할 때 생성되는 draft row)의 `generated_summary`를 LLM으로 채우는 백그라운드 노드를 구현해서, 기능명세 #22(모순 해결 처리) 부분구현 상태를 완성한다.

**Architecture:** `contradiction_detect_node`/`meeting_postprocess_node`와 동일한 단일 노드, 자체 `SessionLocal()` 패턴. AI Chat 노드와 달리 라우터 응답을 기다리지 않는 백그라운드 fire-and-forget (`BackgroundTasks.add_task`) — `ChangeSummaryDraft.generation_status`가 이미 `pending→processing→completed/failed` 상태머신으로 설계되어 있고, 별도 폴링 엔드포인트(`GET .../change-summary`)가 이미 존재하기 때문.

**Tech Stack:** LangGraph(`StateGraph`), Ollama(httpx 직접 호출, 일반 텍스트 응답), SQLAlchemy.

## Global Constraints

- `base_summary_snapshot`/`meeting_summary_id`/`room_id`을 `resolve_contradiction_api`가 채우는 것은 이번 스코프 밖 (라우터 레이어, 지수 파트). 노드는 `base_summary_snapshot`을 선택적 컨텍스트로만 다룬다 (`None`이면 "(추가 맥락 없음)").
- `code_fact` 관련 로직 없음 (이 노드와 무관).
- 이 코드베이스에는 DB/Ollama 목킹 컨벤션이 없다 — 순수 함수(프롬프트 조립)만 유닛테스트로 커버하고, 나머지는 실제 서버 환경(Docker)에서 수동 검증한다.
- CRUD 함수(`update_change_summary_draft`)는 이 코드베이스의 다른 crud 함수들과 마찬가지로 자동화 테스트 없이 코드 리뷰 + 수동 검증으로 확인한다 (기존 crud 함수들도 전부 테스트 없음).

---

### Task 1: `update_change_summary_draft` CRUD 함수 추가

**Files:**
- Modify: `backend/db/crud/contradiction_crud.py`

**Interfaces:**
- Consumes: `backend.db.modules.ChangeSummaryDraft` (이미 import되어 있음), `contradiction_crud.get_change_summary_draft` (기존 함수, 그대로 재사용)
- Produces: `update_change_summary_draft(db: Session, contradiction_id: uuid.UUID, **fields) -> Optional[ChangeSummaryDraft]`

- [ ] **Step 1: `contradiction_crud.py` 맨 끝(`create_change_summary_draft` 함수 뒤)에 함수 추가**

```python
def update_change_summary_draft(
    db: Session, contradiction_id: uuid.UUID, **fields
) -> Optional[ChangeSummaryDraft]:
    """generation_status/generated_summary/generation_error/model_name 등을 부분 갱신한다."""
    row = get_change_summary_draft(db, contradiction_id)
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
    return row
```

- [ ] **Step 2: 문법 확인**

Run: `python -m py_compile backend/db/crud/contradiction_crud.py`
Expected: 에러 없이 종료

- [ ] **Step 3: 커밋**

```bash
git add backend/db/crud/contradiction_crud.py
git commit -m "feat: ChangeSummaryDraft 부분 갱신용 update_change_summary_draft 추가"
```

---

### Task 2: 프롬프트 조립 순수 함수 + 테스트 (TDD)

**Files:**
- Create: `backend/graphs/nodes/change_summary_generate.py` (이 함수들만, 노드 본체는 Task 3)
- Test: `backend/graphs/test_change_summary_graph.py`

**Interfaces:**
- Produces: `build_summary_prompt(original_text: str, accepted_text: str, base_summary: str | None) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/graphs/test_change_summary_graph.py`:

```python
# backend/graphs/test_change_summary_graph.py

from backend.graphs.nodes.change_summary_generate import build_summary_prompt


def test_build_summary_prompt_includes_original_and_accepted():
    prompt = build_summary_prompt("예산 500만원", "예산 800만원", None)
    assert "예산 500만원" in prompt
    assert "예산 800만원" in prompt
    assert "(추가 맥락 없음)" in prompt


def test_build_summary_prompt_includes_base_summary_when_present():
    prompt = build_summary_prompt("A", "B", "이전 회의에서 예산 논의가 있었음")
    assert "이전 회의에서 예산 논의가 있었음" in prompt
    assert "(추가 맥락 없음)" not in prompt


def test_build_summary_prompt_empty_base_summary_string_treated_as_missing():
    prompt = build_summary_prompt("A", "B", "")
    assert "(추가 맥락 없음)" in prompt
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `pytest backend/graphs/test_change_summary_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.graphs.nodes.change_summary_generate'`

- [ ] **Step 3: 최소 구현 작성**

`backend/graphs/nodes/change_summary_generate.py`:

```python
# backend/graphs/nodes/change_summary_generate.py

# 모순을 "변경 인지함"으로 처리한 뒤 생성되는 ChangeSummaryDraft의 요약 텍스트를
# LLM으로 채우는 백그라운드 노드.
#
# contradiction_detect_node/meeting_postprocess_node와 동일한 fire-and-forget
# 패턴 — 라우터 응답과 별개로 백그라운드에서 실행되고, 프론트는
# GET .../change-summary로 폴링한다 (AI Chat 노드와 달리 동기 응답 아님).

import os
import uuid

import httpx

from backend.db.crud import contradiction_crud
from backend.db.session import SessionLocal
from backend.graphs.states.contradiction_resolution_state import ContradictionResolutionState

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

_SUMMARY_PROMPT = """당신은 팀 문서/기록의 변경사항을 정리하는 비서입니다.

[기존 내용]
{original_text}

[새로 확정된 내용]
{accepted_text}

[참고: 관련 회의 요약]
{base_summary}

위 정보를 바탕으로, 무엇이 어떻게 바뀌었는지 팀원들이 한눈에 이해할 수 있도록
간결한 한국어 문장으로 요약하세요 (2~3문장 이내). 다른 설명 없이 요약문만 답하세요."""


def build_summary_prompt(original_text: str, accepted_text: str, base_summary: str | None) -> str:
    """기존 내용 + 새로 확정된 내용 + (있으면) 관련 회의 요약을 프롬프트로 조립한다."""
    return _SUMMARY_PROMPT.format(
        original_text=original_text,
        accepted_text=accepted_text,
        base_summary=base_summary or "(추가 맥락 없음)",
    )
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `pytest backend/graphs/test_change_summary_graph.py -v`
Expected: 3개 테스트 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/graphs/nodes/change_summary_generate.py backend/graphs/test_change_summary_graph.py
git commit -m "feat: 변경요약 프롬프트 조립용 순수 함수 추가"
```

---

### Task 3: 노드 본체 (LLM 호출 + 상태 전이 + 멱등성 가드)

**Files:**
- Modify: `backend/graphs/nodes/change_summary_generate.py` (Task 2 파일에 이어서 추가)

**Interfaces:**
- Consumes: Task 2의 `build_summary_prompt`
- Consumes: `contradiction_crud.get_change_summary_draft(db, contradiction_id) -> Optional[ChangeSummaryDraft]`, `contradiction_crud.update_change_summary_draft(db, contradiction_id, **fields) -> Optional[ChangeSummaryDraft]` (Task 1)
- Consumes: `ChangeSummaryDraft` 필드 — `generation_status`("pending"/"processing"/"completed"/"failed"), `original_reference_text`, `accepted_change_text`, `base_summary_snapshot`, `id`
- Consumes: `backend.graphs.states.contradiction_resolution_state.ContradictionResolutionState` (`contradiction_id` 필드)
- Produces: `change_summary_generate_node(state: ContradictionResolutionState) -> dict` — 반환 dict는 `generated_summary`, `generation_status`, `change_summary_draft_id`, 선택적으로 `model_name`/`error`.

DB/Ollama가 필요해 자동화 테스트 없이 구현 후 Task 6에서 수동 검증한다 (기존 컨벤션).

- [ ] **Step 1: `change_summary_generate.py` 파일 맨 끝에 노드 함수 추가**

```python
def _call_llm_summary(prompt: str) -> str | None:
    """Ollama에 일반 텍스트 요약 생성을 요청한다. 실패 시 None."""
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        response.raise_for_status()
        summary = response.json().get("response", "").strip()
        return summary or None
    except (httpx.HTTPError, ValueError, KeyError, AttributeError) as e:
        print(f"[change_summary_generate] LLM 호출 실패: {repr(e)}")
        return None


def change_summary_generate_node(state: ContradictionResolutionState) -> dict:
    contradiction_uuid = uuid.UUID(state["contradiction_id"])

    db = SessionLocal()
    try:
        draft = contradiction_crud.get_change_summary_draft(db, contradiction_uuid)
        if draft is None:
            return {"error": f"contradiction_id={contradiction_uuid}에 대한 변경요약 초안을 찾을 수 없습니다."}

        # 멱등성 가드 — meeting_postprocess_node의 "processing 아니면 거부"와 동일한 의도.
        # 이미 처리 중/완료/실패한 draft를 중복 실행하지 않는다.
        if draft.generation_status != "pending":
            return {
                "generated_summary": draft.generated_summary,
                "generation_status": draft.generation_status,
                "change_summary_draft_id": str(draft.id),
            }

        contradiction_crud.update_change_summary_draft(
            db, contradiction_uuid, generation_status="processing",
        )

        prompt = build_summary_prompt(
            draft.original_reference_text,
            draft.accepted_change_text,
            draft.base_summary_snapshot,
        )
        summary = _call_llm_summary(prompt)

        if summary is None:
            updated = contradiction_crud.update_change_summary_draft(
                db, contradiction_uuid,
                generation_status="failed",
                generation_error="LLM 호출 실패",
            )
            return {
                "generated_summary": None,
                "generation_status": "failed",
                "change_summary_draft_id": str(updated.id),
            }

        updated = contradiction_crud.update_change_summary_draft(
            db, contradiction_uuid,
            generated_summary=summary,
            generation_status="completed",
            model_name=OLLAMA_MODEL,
        )
        return {
            "generated_summary": summary,
            "generation_status": "completed",
            "model_name": OLLAMA_MODEL,
            "change_summary_draft_id": str(updated.id),
        }

    except Exception as e:
        # meeting_postprocess_node의 finally 패턴과 동일 — draft가 processing에
        # 영원히 멈춰있지 않도록 예상 못 한 예외도 failed로 남긴다.
        print(f"[change_summary_generate] 처리 중 예외 발생: {repr(e)}")
        try:
            contradiction_crud.update_change_summary_draft(
                db, contradiction_uuid,
                generation_status="failed",
                generation_error=repr(e),
            )
        except Exception:
            pass
        return {"error": f"변경요약 생성 중 예외 발생: {repr(e)}"}

    finally:
        db.close()
```

- [ ] **Step 2: Task 2 유닛테스트가 여전히 통과하는지 확인 (import 안 깨졌는지)**

Run: `pytest backend/graphs/test_change_summary_graph.py -v`
Expected: 3개 테스트 전부 PASS

- [ ] **Step 3: 커밋**

```bash
git add backend/graphs/nodes/change_summary_generate.py
git commit -m "feat: 변경요약 생성 노드 본체 구현 (LLM 호출 + 상태 전이 + 멱등성 가드)"
```

---

### Task 4: 그래프 빌더 + 실행 헬퍼

**Files:**
- Create: `backend/graphs/change_summary_graph.py`

**Interfaces:**
- Consumes: `backend.graphs.nodes.change_summary_generate.change_summary_generate_node`, `backend.graphs.states.contradiction_resolution_state.ContradictionResolutionState`
- Produces: `build_change_summary_graph()`, 모듈 레벨 `change_summary_graph`, `run_change_summary_generation(*, contradiction_id: str, workspace_id: str, category_id: str) -> dict`

- [ ] **Step 1: 그래프 파일 작성**

`backend/graphs/change_summary_graph.py`:

```python
# backend/graphs/change_summary_graph.py

from langgraph.graph import END, START, StateGraph

from backend.graphs.nodes.change_summary_generate import change_summary_generate_node
from backend.graphs.states.contradiction_resolution_state import ContradictionResolutionState


def build_change_summary_graph():
    graph = StateGraph(ContradictionResolutionState)
    graph.add_node("change_summary_generate", change_summary_generate_node)
    graph.add_edge(START, "change_summary_generate")
    graph.add_edge("change_summary_generate", END)
    return graph.compile()


change_summary_graph = build_change_summary_graph()


def run_change_summary_generation(
    *, contradiction_id: str, workspace_id: str, category_id: str
) -> dict:
    initial_state: ContradictionResolutionState = {
        "workspace_id": workspace_id,
        "category_id": category_id,
        "contradiction_id": contradiction_id,
    }
    return change_summary_graph.invoke(initial_state)
```

(`resolution_type`/`resolved_by`는 `ContradictionResolutionState`에 `Required`로 선언되어 있지만 TypedDict는 런타임 강제가 없고, 이 노드는 `contradiction_id`만 읽으므로 굳이 채우지 않는다 — `contradiction_detect_node` 호출부도 동일하게 실제 사용하는 필드만 채운다.)

- [ ] **Step 2: import가 깨지지 않는지 확인**

Run: `python -c "from backend.graphs.change_summary_graph import run_change_summary_generation; print('ok')"`
Expected: `ok` 출력

- [ ] **Step 3: 커밋**

```bash
git add backend/graphs/change_summary_graph.py
git commit -m "feat: 변경요약 생성 그래프 빌더 및 실행 헬퍼 추가"
```

---

### Task 5: 노드 exports 등록

**Files:**
- Modify: `backend/graphs/nodes/__init__.py`

- [ ] **Step 1: `__init__.py` 전체를 아래 내용으로 교체**

```python
from backend.graphs.nodes.contradiction_detect import contradiction_detect_node
from backend.graphs.nodes.meeting_postprocess import meeting_postprocess_node
from backend.graphs.nodes.ai_chat_answer import ai_chat_answer_node
from backend.graphs.nodes.change_summary_generate import change_summary_generate_node

__all__ = [
    "contradiction_detect_node",
    "meeting_postprocess_node",
    "ai_chat_answer_node",
    "change_summary_generate_node",
]
```

- [ ] **Step 2: import 확인**

Run: `python -c "from backend.graphs.nodes import change_summary_generate_node; print('ok')"`
Expected: `ok` 출력

- [ ] **Step 3: 커밋**

```bash
git add backend/graphs/nodes/__init__.py
git commit -m "chore: change_summary_generate_node를 graphs.nodes 패키지에 export"
```

---

### Task 6: 라우터 연결

**Files:**
- Modify: `backend/routers/contradiction_router.py`

**Interfaces:**
- Consumes: `backend.graphs.change_summary_graph.run_change_summary_generation`

- [ ] **Step 1: import 추가**

`backend/routers/contradiction_router.py` 상단의

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import contradiction_crud
```

를 아래로 교체:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import contradiction_crud
from backend.graphs.change_summary_graph import run_change_summary_generation
```

- [ ] **Step 2: `resolve_contradiction_api`에 트리거 추가**

기존:

```python
@router.post("/{contradiction_id}/resolve", response_model=ContradictionSchema)
def resolve_contradiction_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    request: ContradictionResolveRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    contradiction = _get_contradiction_or_404(db, contradiction_id, workspace_id)

    if contradiction.status != "unresolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 모순입니다.",
        )

    resolution = contradiction_crud.resolve_contradiction(
        db,
        contradiction_id=contradiction_id,
        resolved_by=uuid.UUID(current_user_id),
        resolution_type=request.resolution_type,
        note=request.note,
    )

    if request.resolution_type == "change_acknowledged":
        # TODO: LLM 기반 변경요약 실제 생성은 후속 작업 — 지금은 draft row만 pending 상태로 생성
        context_type = "meeting" if contradiction.source_type == "meeting_segment" else "chat"
        contradiction_crud.create_change_summary_draft(
            db,
            workspace_id=workspace_id,
            contradiction_id=contradiction_id,
            resolution_id=resolution.id,
            context_type=context_type,
            original_reference_text=contradiction.reference_text_snapshot,
            accepted_change_text=contradiction.statement_text_snapshot,
        )

    updated = contradiction_crud.get_contradiction(db, contradiction_id)
    return ContradictionSchema.model_validate(updated)
```

교체 후:

```python
@router.post("/{contradiction_id}/resolve", response_model=ContradictionSchema)
def resolve_contradiction_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    request: ContradictionResolveRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    contradiction = _get_contradiction_or_404(db, contradiction_id, workspace_id)

    if contradiction.status != "unresolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 모순입니다.",
        )

    resolution = contradiction_crud.resolve_contradiction(
        db,
        contradiction_id=contradiction_id,
        resolved_by=uuid.UUID(current_user_id),
        resolution_type=request.resolution_type,
        note=request.note,
    )

    if request.resolution_type == "change_acknowledged":
        context_type = "meeting" if contradiction.source_type == "meeting_segment" else "chat"
        contradiction_crud.create_change_summary_draft(
            db,
            workspace_id=workspace_id,
            contradiction_id=contradiction_id,
            resolution_id=resolution.id,
            context_type=context_type,
            original_reference_text=contradiction.reference_text_snapshot,
            accepted_change_text=contradiction.statement_text_snapshot,
        )
        # 요약 생성은 백그라운드로 — 응답은 draft가 pending인 채로 바로 나가고,
        # 프론트는 GET .../change-summary로 완료 여부를 폴링한다.
        background_tasks.add_task(
            run_change_summary_generation,
            contradiction_id=str(contradiction_id),
            workspace_id=str(workspace_id),
            category_id=str(contradiction.category_id),
        )

    updated = contradiction_crud.get_contradiction(db, contradiction_id)
    return ContradictionSchema.model_validate(updated)
```

- [ ] **Step 3: 유닛 테스트 재실행 (회귀 확인)**

Run: `pytest backend/graphs/test_change_summary_graph.py -v`
Expected: 3개 테스트 전부 PASS

- [ ] **Step 4: 커밋**

```bash
git add backend/routers/contradiction_router.py
git commit -m "feat: 모순 해결 라우터를 변경요약 생성 그래프에 연결"
```

---

### Task 7: 수동 통합 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: 서버(Docker) 환경에서 유닛테스트 재확인**

AI Chat 노드 검증 때와 동일하게, 86서버의 `ai-chat-verify` 이미지(또는 재빌드본) 안에서:

```bash
docker run --rm ai-chat-verify sh -c "pip install --quiet pytest sqlalchemy psycopg2-binary -r backend/backend_requirements.txt && pytest backend/graphs/test_change_summary_graph.py -v"
```
Expected: 3개 테스트 PASS

- [ ] **Step 2: 모순 하나를 "변경 인지함"으로 처리**

```bash
curl -X POST http://localhost:8000/api/workspaces/{workspace_id}/contradictions/{contradiction_id}/resolve \
  -H "Authorization: Bearer {token}" -H "Content-Type: application/json" \
  -d '{"resolution_type": "change_acknowledged"}'
```
Expected: 200 응답, 모순 status가 "resolved"로 바뀜 (아직 요약은 안 끝났을 수 있음)

- [ ] **Step 3: 변경요약 폴링 확인**

```bash
curl http://localhost:8000/api/workspaces/{workspace_id}/contradictions/{contradiction_id}/change-summary \
  -H "Authorization: Bearer {token}"
```
몇 초 뒤 재요청 시 `generation_status`가 `pending` → `processing` → `completed`로 바뀌고 `generated_summary`에 실제 요약 텍스트가 채워지는지 확인.

- [ ] **Step 4: Ollama 잠시 중지하고 실패 폴백 확인 (선택)**

Ollama 중지 후 다른 모순으로 2~3단계 반복 → `generation_status`가 `failed`, `generation_error`에 "LLM 호출 실패"가 들어가는지 확인. 확인 후 Ollama 재시작.
