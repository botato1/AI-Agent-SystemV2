# AI Chat 답변 생성 노드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ai_chat_router.py`의 `_generate_ai_response` 스텁(NotImplementedError, 항상 503)을 실제 LangGraph 노드로 교체해서, AI Chat 질문에 문서+회의 RAG 검색 기반 답변을 생성한다.

**Architecture:** `contradiction_detect_node`/`meeting_postprocess_node`와 같은 단일 노드 그래프. 단, 이 노드는 **DB에 아무것도 쓰지 않는다** — 라우터가 이미 `ai_chat_crud.add_ai_exchange()`로 user+assistant 메시지와 sources를 한 트랜잭션에 저장하는 구조로 되어 있으므로(답변 생성 성공 후에만 저장), 노드는 순수하게 "검색+생성"만 하고 `(answer, sources)`를 반환한다.

**Tech Stack:** LangGraph(`StateGraph`), ChromaDB(`search_hybrid`), Ollama(httpx 직접 호출), SQLAlchemy(`content_chunk_crud`, 읽기 전용).

## Global Constraints

- `search_hybrid()`는 `collection_name`에 문자열 하나 또는 `None`(전체 4개 컬렉션)만 받고 리스트는 못 받는다 — `DOCUMENT_COLLECTION`/`MEETING_COLLECTION` 각각 별도 호출 필요.
- `code_fact` 소스 타입은 이번 스코프에서 제외한다 (모델/CRUD 자체가 레포에 없음, `git grep -r code_fact` 확인됨).
- 노드는 채팅 메시지를 저장하지 않는다. 저장은 전부 라우터의 `ai_chat_crud.add_ai_exchange()`가 담당한다.
- 이 코드베이스에는 DB/Chroma/Ollama용 목킹 컨벤션이 없다(`backend/graphs/test_contradiction_graph.py` 참조) — 순수 함수(입출력에 I/O 없는 함수)만 유닛 테스트로 커버하고, 나머지는 수동 검증한다.
- Ollama 호출은 다른 노드와 동일하게 `OLLAMA_BASE_URL`/`OLLAMA_MODEL` 환경변수 사용, 실패 시 예외를 올리지 말고 안내 문구로 폴백한다.

---

### Task 1: 순수 헬퍼 함수 (검색결과 병합, 대화이력 포맷, 프롬프트 조립)

**Files:**
- Create: `backend/graphs/nodes/ai_chat_answer.py` (헬퍼 함수만, 노드 함수는 Task 2)
- Test: `backend/graphs/test_ai_chat_graph.py`

**Interfaces:**
- Produces: `merge_and_rank_candidates(doc_results: list[dict], meeting_results: list[dict], top_k: int = 5) -> list[dict]`
- Produces: `format_chat_history(chat_history: list[dict] | None, max_turns: int = 3) -> str`
- Produces: `build_answer_prompt(context_texts: list[str], chat_history: list[dict] | None, question: str) -> str`
- Produces: 상수 `NO_RESULTS_ANSWER`, `LLM_FAILURE_ANSWER`, `TOP_K_PER_COLLECTION`, `TOP_K_FINAL`, `CHAT_HISTORY_TURNS`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/graphs/test_ai_chat_graph.py`:

```python
# backend/graphs/test_ai_chat_graph.py

from backend.graphs.nodes.ai_chat_answer import (
    merge_and_rank_candidates,
    format_chat_history,
    build_answer_prompt,
)


def test_merge_and_rank_candidates_orders_by_score():
    doc_results = [{"id": "d1", "score": 0.9}, {"id": "d2", "score": 0.3}]
    meeting_results = [{"id": "m1", "score": 0.95}, {"id": "m2", "score": 0.5}]

    result = merge_and_rank_candidates(doc_results, meeting_results, top_k=3)

    assert [r["id"] for r in result] == ["m1", "d1", "m2"]


def test_merge_and_rank_candidates_empty_inputs():
    assert merge_and_rank_candidates([], [], top_k=5) == []


def test_merge_and_rank_candidates_respects_top_k():
    doc_results = [{"id": f"d{i}", "score": i / 10} for i in range(10)]
    result = merge_and_rank_candidates(doc_results, [], top_k=3)
    assert len(result) == 3
    assert result[0]["id"] == "d9"


def test_format_chat_history_empty():
    assert format_chat_history(None) == "(이전 대화 없음)"
    assert format_chat_history([]) == "(이전 대화 없음)"


def test_format_chat_history_truncates_to_recent_turns():
    history = [
        {"role": "user", "content": f"질문{i}"} if i % 2 == 0 else {"role": "assistant", "content": f"답변{i}"}
        for i in range(10)
    ]
    result = format_chat_history(history, max_turns=2)
    lines = result.split("\n")

    assert len(lines) == 4
    assert "질문8" in result
    assert "질문0" not in result


def test_format_chat_history_labels_roles():
    history = [{"role": "user", "content": "안녕"}, {"role": "assistant", "content": "네 안녕하세요"}]
    result = format_chat_history(history)
    assert "사용자: 안녕" in result
    assert "AI: 네 안녕하세요" in result


def test_build_answer_prompt_includes_context_and_question():
    prompt = build_answer_prompt(["문서 내용 A"], None, "질문입니다")
    assert "문서 내용 A" in prompt
    assert "질문입니다" in prompt
    assert "(이전 대화 없음)" in prompt


def test_build_answer_prompt_empty_context():
    prompt = build_answer_prompt([], None, "질문")
    assert "(근거 자료 없음)" in prompt
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `pytest backend/graphs/test_ai_chat_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.graphs.nodes.ai_chat_answer'` (아직 파일이 없음)

- [ ] **Step 3: 최소 구현 작성**

`backend/graphs/nodes/ai_chat_answer.py`:

```python
# backend/graphs/nodes/ai_chat_answer.py

# 채팅방별 개인 AI Chat 세션에서 질문에 답하는 노드.
# 문서(DOCUMENT_COLLECTION)+회의(MEETING_COLLECTION)를 RAG로 검색해서
# 근거 기반 답변을 생성한다.
#
# 주의: 이 노드는 DB에 아무것도 쓰지 않는다. 채팅 메시지/근거자료 저장은
# 답변 생성이 성공한 뒤 라우터가 ai_chat_crud.add_ai_exchange()로
# 한 번에 처리한다 (실패 시 "답변 없는 질문"만 남는 것을 방지하기 위함).

import os

TOP_K_PER_COLLECTION = 5
TOP_K_FINAL = 5
CHAT_HISTORY_TURNS = 3

NO_RESULTS_ANSWER = "업로드된 자료에서 관련 내용을 찾지 못했습니다. 다른 표현으로 다시 질문해주시겠어요?"
LLM_FAILURE_ANSWER = "지금은 답변을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."

_ANSWER_PROMPT = """당신은 팀 워크스페이스에 업로드된 문서와 회의 내용을 바탕으로 질문에 답하는 도우미입니다.

[근거 자료]
{context}

[최근 대화]
{history}

[질문]
{question}

근거 자료에 있는 내용만 바탕으로 답하세요. 근거 자료에 없는 내용은 답하지 말고 모른다고 답하세요.
자연스러운 한국어 문장으로 답하세요 (JSON이나 마크다운 형식 없이 답변 텍스트만)."""


def merge_and_rank_candidates(
    doc_results: list[dict], meeting_results: list[dict], top_k: int = TOP_K_FINAL
) -> list[dict]:
    """문서/회의 검색 결과를 score 기준으로 병합 정렬한다.

    search_hybrid()는 collection_name에 컬렉션 하나만 받을 수 있어
    문서/회의를 각각 따로 검색한 뒤 여기서 합친다.
    """
    combined = list(doc_results) + list(meeting_results)
    combined.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return combined[:top_k]


def format_chat_history(chat_history: list[dict] | None, max_turns: int = CHAT_HISTORY_TURNS) -> str:
    """chat_history({"role","content"} 딕셔너리 리스트)를 프롬프트용 텍스트로 변환한다."""
    if not chat_history:
        return "(이전 대화 없음)"
    recent = chat_history[-(max_turns * 2):]
    lines = [f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in recent]
    return "\n".join(lines)


def build_answer_prompt(context_texts: list[str], chat_history: list[dict] | None, question: str) -> str:
    """검색된 청크 본문 + 대화 이력 + 질문을 하나의 프롬프트로 조립한다."""
    context = "\n\n---\n\n".join(context_texts) if context_texts else "(근거 자료 없음)"
    history = format_chat_history(chat_history)
    return _ANSWER_PROMPT.format(context=context, history=history, question=question)
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `pytest backend/graphs/test_ai_chat_graph.py -v`
Expected: 8개 테스트 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/graphs/nodes/ai_chat_answer.py backend/graphs/test_ai_chat_graph.py
git commit -m "feat: AI Chat 답변 프롬프트 조립용 순수 헬퍼 함수 추가"
```

---

### Task 2: 노드 본체 (검색 + LLM 호출 + 폴백 처리)

**Files:**
- Modify: `backend/graphs/nodes/ai_chat_answer.py` (Task 1 파일에 이어서 추가)

**Interfaces:**
- Consumes: Task 1의 `merge_and_rank_candidates`, `build_answer_prompt`, `NO_RESULTS_ANSWER`, `LLM_FAILURE_ANSWER`, `TOP_K_PER_COLLECTION`, `TOP_K_FINAL`
- Consumes: `backend.modules.rag.chroma_client.search_hybrid(query_text, workspace_id, category_id, top_k, collection_name) -> list[dict]` (각 dict는 `id`, `score`, `content` 등을 가짐 — `backend/graphs/nodes/contradiction_detect.py`에서 동일 함수 사용 중)
- Consumes: `backend.db.crud.content_chunk_crud.get_chunk_by_chroma_id(db, chroma_id) -> ContentChunk | None` (`.chunk_text`, `.file_id`, `.id` 속성)
- Consumes: `backend.db.session.SessionLocal`
- Consumes: `backend.graphs.states.ai_chat_state.AIChatState` (`workspace_id`, `category_id`, `user_message`, `chat_history` 필드)
- Produces: `ai_chat_answer_node(state: AIChatState) -> dict` — 반환 dict는 `answer: str`, `chunk_search_results: list[dict]`, `retrieved_sources: list[dict]`, 선택적으로 `answer_model_name: str`, `error: str`. `retrieved_sources`의 각 원소는 `{"source_type": "content_chunk", "file_id": UUID, "chunk_id": UUID, "similarity_score": float, "display_order": int}` 형태 — `ai_chat_crud.add_ai_exchange()`의 `sources` 인자와 그대로 호환.

이 단계는 실제 Chroma/Ollama/DB 호출이 필요해 자동화 테스트 없이 구현 후 Task 6에서 수동 검증한다 (코드베이스 기존 컨벤션).

- [ ] **Step 1: `ai_chat_answer.py`에 import와 노드 함수 추가**

파일 상단(기존 `import os` 아래)에 추가:

```python
import httpx

from backend.db.crud import content_chunk_crud
from backend.db.session import SessionLocal
from backend.graphs.states.ai_chat_state import AIChatState
from backend.modules.rag.chroma_client import DOCUMENT_COLLECTION, MEETING_COLLECTION, search_hybrid

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
```

파일 맨 끝에 추가:

```python
def _call_llm_answer(prompt: str) -> str | None:
    """Ollama에 일반 텍스트 답변 생성을 요청한다. 실패 시 None (다른 노드처럼 JSON 강제 안 함 — 채팅 답변은 텍스트 그대로 노출)."""
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        response.raise_for_status()
        answer = response.json().get("response", "").strip()
        return answer or None
    except (httpx.HTTPError, ValueError, KeyError, AttributeError) as e:
        print(f"[ai_chat_answer] LLM 호출 실패: {repr(e)}")
        return None


def ai_chat_answer_node(state: AIChatState) -> dict:
    workspace_id = state["workspace_id"]
    category_id = state["category_id"]
    user_message = state["user_message"]
    chat_history = state.get("chat_history")

    try:
        doc_results = search_hybrid(
            query_text=user_message, workspace_id=workspace_id, category_id=category_id,
            top_k=TOP_K_PER_COLLECTION, collection_name=DOCUMENT_COLLECTION,
        )
        meeting_results = search_hybrid(
            query_text=user_message, workspace_id=workspace_id, category_id=category_id,
            top_k=TOP_K_PER_COLLECTION, collection_name=MEETING_COLLECTION,
        )
    except Exception as e:
        print(f"[ai_chat_answer] 검색 실패: {repr(e)}")
        doc_results, meeting_results = [], []

    candidates = merge_and_rank_candidates(doc_results, meeting_results, top_k=TOP_K_FINAL)

    if not candidates:
        return {
            "answer": NO_RESULTS_ANSWER,
            "chunk_search_results": [],
            "retrieved_sources": [],
        }

    db = SessionLocal()
    try:
        resolved = []
        for candidate in candidates:
            chunk = content_chunk_crud.get_chunk_by_chroma_id(db, candidate["id"])
            if chunk:
                # ChromaDB엔 있는데 Postgres 쪽 원본 청크가 없는 경우(고아 데이터) — 스킵
                resolved.append((candidate, chunk))
    finally:
        db.close()

    if not resolved:
        return {
            "answer": NO_RESULTS_ANSWER,
            "chunk_search_results": candidates,
            "retrieved_sources": [],
        }

    context_texts = [chunk.chunk_text for _, chunk in resolved]
    prompt = build_answer_prompt(context_texts, chat_history, user_message)
    answer = _call_llm_answer(prompt)

    if answer is None:
        return {
            "answer": LLM_FAILURE_ANSWER,
            "chunk_search_results": candidates,
            "retrieved_sources": [],
            "error": "LLM 호출 실패",
        }

    sources = [
        {
            "source_type": "content_chunk",
            "file_id": chunk.file_id,
            "chunk_id": chunk.id,
            "similarity_score": candidate.get("score"),
            "display_order": i,
        }
        for i, (candidate, chunk) in enumerate(resolved)
    ]

    return {
        "answer": answer,
        "answer_model_name": OLLAMA_MODEL,
        "chunk_search_results": candidates,
        "retrieved_sources": sources,
    }
```

- [ ] **Step 2: 기존 유닛 테스트가 여전히 통과하는지 확인 (import 에러 없는지)**

Run: `pytest backend/graphs/test_ai_chat_graph.py -v`
Expected: 8개 테스트 전부 PASS (import 경로가 깨지지 않았는지 확인하는 용도)

- [ ] **Step 3: 커밋**

```bash
git add backend/graphs/nodes/ai_chat_answer.py
git commit -m "feat: AI Chat 답변 생성 노드 구현 (RAG 검색 + LLM 호출)"
```

---

### Task 3: 그래프 빌더 + 실행 헬퍼

**Files:**
- Create: `backend/graphs/ai_chat_graph.py`

**Interfaces:**
- Consumes: `backend.graphs.nodes.ai_chat_answer.ai_chat_answer_node`, `backend.graphs.states.ai_chat_state.AIChatState`
- Produces: `build_ai_chat_graph()`, 모듈 레벨 `ai_chat_graph`, `run_ai_chat_answer(*, session_id: str, workspace_id: str, category_id: str, room_id: str, user_id: str, user_message: str, chat_history: list[dict] | None = None) -> dict` — 반환값은 그래프 최종 state(dict), `result["answer"]`/`result.get("retrieved_sources", [])`로 접근

- [ ] **Step 1: 그래프 파일 작성**

`backend/graphs/ai_chat_graph.py`:

```python
# backend/graphs/ai_chat_graph.py

from langgraph.graph import END, START, StateGraph

from backend.graphs.nodes.ai_chat_answer import ai_chat_answer_node
from backend.graphs.states.ai_chat_state import AIChatState


def build_ai_chat_graph():
    graph = StateGraph(AIChatState)
    graph.add_node("ai_chat_answer", ai_chat_answer_node)
    graph.add_edge(START, "ai_chat_answer")
    graph.add_edge("ai_chat_answer", END)
    return graph.compile()


ai_chat_graph = build_ai_chat_graph()


def run_ai_chat_answer(
    *,
    session_id: str,
    workspace_id: str,
    category_id: str,
    room_id: str,
    user_id: str,
    user_message: str,
    chat_history: list[dict] | None = None,
) -> dict:
    initial_state: AIChatState = {
        "workspace_id": workspace_id,
        "category_id": category_id,
        "session_id": session_id,
        "room_id": room_id,
        "user_id": user_id,
        "user_message": user_message,
    }
    if chat_history is not None:
        initial_state["chat_history"] = chat_history
    return ai_chat_graph.invoke(initial_state)
```

- [ ] **Step 2: import가 깨지지 않는지 확인**

Run: `python -c "from backend.graphs.ai_chat_graph import run_ai_chat_answer; print('ok')"`
Expected: `ok` 출력 (langgraph/DB 연결 등은 이 시점에 실행 안 되므로 에러 없이 import만 성공하면 됨)

- [ ] **Step 3: 커밋**

```bash
git add backend/graphs/ai_chat_graph.py
git commit -m "feat: AI Chat 답변 생성 그래프 빌더 및 실행 헬퍼 추가"
```

---

### Task 4: 노드 exports 등록

**Files:**
- Modify: `backend/graphs/nodes/__init__.py`

**Interfaces:**
- Consumes: `backend.graphs.nodes.ai_chat_answer.ai_chat_answer_node`

- [ ] **Step 1: `__init__.py` 전체를 아래 내용으로 교체**

```python
from backend.graphs.nodes.contradiction_detect import contradiction_detect_node
from backend.graphs.nodes.meeting_postprocess import meeting_postprocess_node
from backend.graphs.nodes.ai_chat_answer import ai_chat_answer_node

__all__ = [
    "contradiction_detect_node",
    "meeting_postprocess_node",
    "ai_chat_answer_node",
]
```

- [ ] **Step 2: import 확인**

Run: `python -c "from backend.graphs.nodes import ai_chat_answer_node; print('ok')"`
Expected: `ok` 출력

- [ ] **Step 3: 커밋**

```bash
git add backend/graphs/nodes/__init__.py
git commit -m "chore: ai_chat_answer_node를 graphs.nodes 패키지에 export"
```

---

### Task 4.5: `get_documents_by_room_id` 등 rag_service.py 스텁 정리 확인 (변경 없음, 확인만)

이번 작업은 `rag_service.py`를 건드리지 않는다 (그 파일의 `get_documents_by_room_id`/`get_document_by_title_and_room`는 legacy room 기반 개념이고, AI Chat 노드는 `search_hybrid`를 workspace_id/category_id로 직접 호출하므로 이 스텁들과 무관하다). 별도 정리 작업이 필요하면 후속 티켓으로 분리한다 — 이 플랜의 스코프 밖.

---

### Task 5: 라우터 연결

**Files:**
- Modify: `backend/routers/ai_chat_router.py`

**Interfaces:**
- Consumes: `backend.graphs.ai_chat_graph.run_ai_chat_answer`
- Consumes: `backend.db.crud.ai_chat_crud.get_session_history(db, session_id) -> list[AiChatMessage]` (기존 함수, role/content 속성 보유)
- Consumes: `backend.db.crud.ai_chat_crud.add_ai_exchange(db, *, session_id, user_content, assistant_content, sources=None, model_name=None) -> AiChatMessage` (기존 함수, 변경 없음)

- [ ] **Step 1: import 교체**

`backend/routers/ai_chat_router.py` 상단의

```python
from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import ai_chat_crud, room_crud
```

를 아래로 교체:

```python
from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import ai_chat_crud, room_crud
from backend.graphs.ai_chat_graph import run_ai_chat_answer
```

- [ ] **Step 2: `_generate_ai_response` 스텁 삭제**

아래 블록을 통째로 삭제:

```python
# TODO(가동현): RAG 그래프 노드 연결 예정. 지금은 답변 생성 부분만 스텁 처리.
def _generate_ai_response(session_id: UUID, question: str) -> tuple[str, list[dict]]:
    """가동현님의 RAG 그래프 노드가 준비되면 이 함수를 실제 호출로 교체."""
    raise NotImplementedError("AI 답변 생성 그래프가 아직 연결되지 않았습니다.")
```

- [ ] **Step 3: `send_ai_chat_message` 본문 교체**

기존:

```python
def send_ai_chat_message(
    workspace_id: UUID,
    room_id: UUID,
    request: AIChatMessageCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    session = ai_chat_crud.get_or_create_session(db, workspace_id, room_id, UUID(current_user_id))

    # 답변 생성을 먼저 시도하고 성공했을 때만 메시지를 저장한다.
    # (실패 시 대화기록에 "답변 없는 질문"만 남는 것을 방지)
    try:
        answer, sources = _generate_ai_response(session.id, request.content)
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 답변 생성 기능은 아직 사용할 수 없습니다.",
        )

    assistant_message = ai_chat_crud.add_ai_exchange(
        db,
        session_id=session.id,
        user_content=request.content,
        assistant_content=answer,
        sources=sources,
    )
    return AIChatMessageSchema.model_validate(assistant_message)
```

교체 후:

```python
def send_ai_chat_message(
    workspace_id: UUID,
    room_id: UUID,
    request: AIChatMessageCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    room = _get_room_or_404(db, room_id, workspace_id)

    session = ai_chat_crud.get_or_create_session(db, workspace_id, room_id, UUID(current_user_id))

    # 답변 생성 노드에 넘길 대화 이력 — 이번 질문을 저장하기 전 시점의 기록만 사용
    # (저장 후 조회하면 방금 보낸 질문이 "이전 대화"에 중복으로 들어감)
    history_rows = ai_chat_crud.get_session_history(db, session.id)
    chat_history = [
        {"role": m.role, "content": m.content}
        for m in history_rows
        if m.role in ("user", "assistant")
    ]

    result = run_ai_chat_answer(
        session_id=str(session.id),
        workspace_id=str(workspace_id),
        category_id=str(room.category_id),
        room_id=str(room_id),
        user_id=current_user_id,
        user_message=request.content,
        chat_history=chat_history,
    )
    answer = result.get("answer") or "지금은 답변을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."
    sources = result.get("retrieved_sources") or []

    # 답변 생성을 먼저 시도하고 성공했을 때만 메시지를 저장한다.
    # (실패 시 대화기록에 "답변 없는 질문"만 남는 것을 방지)
    assistant_message = ai_chat_crud.add_ai_exchange(
        db,
        session_id=session.id,
        user_content=request.content,
        assistant_content=answer,
        sources=sources,
        model_name=result.get("answer_model_name"),
    )
    return AIChatMessageSchema.model_validate(assistant_message)
```

- [ ] **Step 4: 유닛 테스트 재실행 (회귀 확인)**

Run: `pytest backend/graphs/test_ai_chat_graph.py -v`
Expected: 8개 테스트 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/routers/ai_chat_router.py
git commit -m "feat: AI Chat 라우터를 답변 생성 그래프에 연결"
```

---

### Task 6: 수동 통합 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: 로컬 서버 기동**

Run: `uvicorn backend.main:app --reload` (Ollama/ChromaDB가 이미 떠 있어야 함)

- [ ] **Step 2: 문서가 없는 워크스페이스에서 질문 — "관련 내용 없음" 분기 확인**

```bash
curl -X POST http://localhost:8000/api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat/messages \
  -H "Authorization: Bearer {token}" -H "Content-Type: application/json" \
  -d '{"content": "전혀 관련 없는 질문 아무거나"}'
```
Expected: `content`가 `NO_RESULTS_ANSWER` 문구, 200 응답 (503 아님)

- [ ] **Step 3: 문서가 업로드된 워크스페이스에서 실제 내용 기반 질문**

같은 엔드포인트로 업로드된 문서 내용과 관련된 질문 전송.
Expected: 200 응답, `content`에 문서 내용을 반영한 답변이 옴 (환각 없이 실제 문서 근거 기반인지 육안 확인)

- [ ] **Step 4: 근거자료 조회 확인**

```bash
curl http://localhost:8000/api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat/messages/{message_id}/sources \
  -H "Authorization: Bearer {token}"
```
Expected: Step 3 답변에 사용된 청크들이 `source_type: "content_chunk"`로 나열됨

- [ ] **Step 5: 후속 질문(대화 맥락 유지) 확인**

Step 3 질문 이후 "그럼 그건 언제부터야?" 같은 후속 질문 전송 — `chat_history`가 프롬프트에 반영돼 맥락 있는 답변이 나오는지 확인.

- [ ] **Step 6: Ollama 강제로 끄고 폴백 확인 (선택)**

Ollama 프로세스를 잠시 중지한 뒤 질문 전송 → `LLM_FAILURE_ANSWER` 문구로 응답하고 500이 아닌지 확인. 확인 후 Ollama 재시작.
