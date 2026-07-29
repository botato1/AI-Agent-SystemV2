# backend/graphs/nodes/ai_chat_answer.py

# 채팅방별 개인 AI Chat 세션에서 질문에 답하는 노드.
# 문서(DOCUMENT_COLLECTION)+회의(MEETING_COLLECTION)+결정사항(DECISION_COLLECTION)을
# RAG로 검색해서 근거 기반 답변을 생성한다.
#
# 주의: 이 노드는 DB에 아무것도 쓰지 않는다. 채팅 메시지/근거자료 저장은
# 답변 생성이 성공한 뒤 라우터가 ai_chat_crud.add_ai_exchange()로
# 한 번에 처리한다 (실패 시 "답변 없는 질문"만 남는 것을 방지하기 위함).

import os
import uuid

import httpx

from backend.db.crud import content_chunk_crud
from backend.db.modules import Decision
from backend.db.session import SessionLocal
from backend.graphs.states.ai_chat_state import AIChatState
from backend.modules.rag.chroma_client import (
    DECISION_COLLECTION,
    DOCUMENT_COLLECTION,
    MEETING_COLLECTION,
    search_hybrid,
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

TOP_K_PER_COLLECTION = 5
TOP_K_FINAL = 5
CHAT_HISTORY_TURNS = 3
# rag_service.py의 실측 기준 주석("8개 질문 실측: 관련있음 0.6~0.99, 무관 0.4 미만")과
# 동일한 임계값 사용 — ChromaDB는 컬렉션에 데이터가 있으면 관련성과 무관하게
# 최근접 결과를 반환하므로, 이 이상인 결과만 실제 근거로 취급한다.
MIN_RELEVANCE_SCORE = 0.4

NO_RESULTS_ANSWER = "업로드된 자료에서 관련 내용을 찾지 못했습니다. 다른 표현으로 다시 질문해주시겠어요?"
LLM_FAILURE_ANSWER = "지금은 답변을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."
SEARCH_FAILURE_ANSWER = "지금은 검색 시스템에 문제가 있어 답변을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."

_ANSWER_PROMPT = """당신은 팀 워크스페이스에 업로드된 문서, 회의 내용, 확정된 결정사항을 바탕으로 질문에 답하는 도우미입니다.

[근거 자료]
{context}

[최근 대화]
{history}

[질문]
{question}

근거 자료에 있는 내용만 바탕으로 답하세요. 근거 자료에 없는 내용은 답하지 말고 모른다고 답하세요.
자연스러운 한국어 문장으로 답하세요 (JSON이나 마크다운 형식 없이 답변 텍스트만)."""


def merge_and_rank_candidates(
    doc_results: list[dict],
    meeting_results: list[dict],
    decision_results: list[dict] | None = None,
    top_k: int = TOP_K_FINAL,
) -> list[dict]:
    """문서/회의/결정사항 검색 결과를 score 기준으로 병합 정렬한다.

    search_hybrid()는 collection_name에 컬렉션 하나만 받을 수 있어
    문서/회의/결정사항을 각각 따로 검색한 뒤 여기서 합친다.
    decision_results는 선택값 — 생략하면 기존 문서/회의 2종 병합과 동일하게 동작한다.
    """
    combined = list(doc_results) + list(meeting_results) + list(decision_results or [])
    combined.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return combined[:top_k]


def filter_by_relevance(candidates: list[dict], min_score: float = MIN_RELEVANCE_SCORE) -> list[dict]:
    """검색 점수가 임계값 미만인 후보를 제거한다.

    ChromaDB는 컬렉션에 데이터가 있기만 하면 질문과 무관해도 "가장 가까운" 결과를
    반환하므로, 임계값 없이는 NO_RESULTS_ANSWER가 사실상 컬렉션이 완전히 비어있을
    때만 동작하게 된다.
    """
    return [c for c in candidates if c.get("score", 0.0) >= min_score]


def clamp_similarity_score(score) -> float:
    """search_hybrid의 score(semantic*0.7 + keyword*0.3 가중합)가 이론상 [0,1]을
    벗어날 수 있어, AiMessageSourceSchema의 ge=0/le=1 제약과 충돌하지 않도록
    저장 전에 clamp한다."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, value))


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
        decision_results = search_hybrid(
            query_text=user_message, workspace_id=workspace_id, category_id=category_id,
            top_k=TOP_K_PER_COLLECTION, collection_name=DECISION_COLLECTION,
        )
    except Exception as e:
        print(f"[ai_chat_answer] 검색 실패: {repr(e)}")
        doc_results, meeting_results, decision_results = [], [], []

    candidates = merge_and_rank_candidates(doc_results, meeting_results, decision_results, top_k=TOP_K_FINAL)
    candidates = filter_by_relevance(candidates)

    if not candidates:
        return {
            "answer": NO_RESULTS_ANSWER,
            "chunk_search_results": [],
            "retrieved_sources": [],
        }

    try:
        db = SessionLocal()
        try:
            workspace_uuid = uuid.UUID(workspace_id)
            category_uuid = uuid.UUID(category_id)
            # rag_enabled/is_latest/분석완료/미삭제 조건을 만족하는 파일만 근거로 허용
            allowed_file_ids = {
                row.id
                for row in content_chunk_crud.list_rag_searchable_chunk_files(db, workspace_uuid)
            }

            # (candidate, kind, chunk_또는_decision) — decision은 content_chunks에 없어서
            # 완전히 다른 테이블/조건으로 역참조해야 한다 (chroma_id로 못 찾음).
            resolved: list[tuple[dict, str, object]] = []
            for candidate in candidates:
                if candidate.get("collection") == DECISION_COLLECTION:
                    decision_id_str = candidate.get("document_id") or candidate.get("id")
                    try:
                        decision = db.get(Decision, uuid.UUID(decision_id_str))
                    except (TypeError, ValueError):
                        continue
                    if not decision or decision.workspace_id != workspace_uuid:
                        continue
                    if decision.status != "active":
                        # superseded/cancelled된 결정은 이제 유효하지 않으므로 근거로 안 씀
                        continue
                    resolved.append((candidate, "decision", decision))
                    continue

                chunk = content_chunk_crud.get_chunk_by_chroma_id(db, candidate["id"])
                if chunk is None:
                    # ChromaDB엔 있는데 Postgres 쪽 원본 청크가 없는 경우(고아 데이터) — 스킵
                    continue
                if (
                    chunk.workspace_id != workspace_uuid
                    or chunk.category_id != category_uuid
                    or chunk.file_id not in allowed_file_ids
                ):
                    # 요청 범위와 다른 워크스페이스/카테고리이거나, 원본 파일이 삭제/구버전/
                    # 미완료 분석 상태인 청크는 근거로 쓰지 않는다.
                    continue
                resolved.append((candidate, "content_chunk", chunk))
        finally:
            db.close()
    except Exception as e:
        print(f"[ai_chat_answer] DB 역참조 실패: {repr(e)}")
        return {
            "answer": SEARCH_FAILURE_ANSWER,
            "chunk_search_results": candidates,
            "retrieved_sources": [],
            "error": f"DB 역참조 실패: {repr(e)}",
        }

    if not resolved:
        return {
            "answer": NO_RESULTS_ANSWER,
            "chunk_search_results": candidates,
            "retrieved_sources": [],
        }

    context_texts = []
    for _, kind, obj in resolved:
        if kind == "decision":
            text = obj.decision_text if not obj.reason else f"{obj.decision_text}\n(결정 이유: {obj.reason})"
            context_texts.append(text)
        else:
            context_texts.append(obj.chunk_text)

    prompt = build_answer_prompt(context_texts, chat_history, user_message)
    answer = _call_llm_answer(prompt)

    if answer is None:
        return {
            "answer": LLM_FAILURE_ANSWER,
            "chunk_search_results": candidates,
            "retrieved_sources": [],
            "error": "LLM 호출 실패",
        }

    sources = []
    for i, (candidate, kind, obj) in enumerate(resolved):
        score = clamp_similarity_score(candidate.get("score"))
        if kind == "decision":
            sources.append({
                "source_type": "decision",
                "decision_id": obj.id,
                "similarity_score": score,
                "display_order": i,
            })
        else:
            sources.append({
                "source_type": "content_chunk",
                "file_id": obj.file_id,
                "chunk_id": obj.id,
                "similarity_score": score,
                "display_order": i,
            })

    return {
        "answer": answer,
        "answer_model_name": OLLAMA_MODEL,
        "chunk_search_results": candidates,
        "retrieved_sources": sources,
    }
