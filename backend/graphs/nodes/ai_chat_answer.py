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
