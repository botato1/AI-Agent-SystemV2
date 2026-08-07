# backend/graphs/nodes/ai_chat_answer.py

# 채팅방별 개인 AI Chat 세션에서 질문에 답하는 노드.
# 문서(DOCUMENT_COLLECTION)+회의(MEETING_COLLECTION)+결정사항(DECISION_COLLECTION)을
# RAG로 검색해서 근거 기반 답변을 생성한다.
#
# 주의: 이 노드는 DB에 아무것도 쓰지 않는다. 채팅 메시지/근거자료 저장은
# 답변 생성이 성공한 뒤 라우터가 ai_chat_crud.add_ai_exchange()로
# 한 번에 처리한다 (실패 시 "답변 없는 질문"만 남는 것을 방지하기 위함).

import re
import uuid

import httpx

from backend.db.crud import content_chunk_crud
from backend.db.modules import Decision
from backend.db.session import SessionLocal
from backend.graphs.states.ai_chat_state import AIChatState
from backend.modules.llm.ollama_client import OLLAMA_MODEL_HEAVY, _call_ollama
from backend.modules.rag.chroma_client import (
    DECISION_COLLECTION,
    DOCUMENT_COLLECTION,
    MEETING_COLLECTION,
    rerank_results,
    search_hybrid,
)

# [수정] 자체 OLLAMA_MODEL/httpx 직접 호출을 걷어내고 공용 ollama_client를 쓴다.
# - 모델: 문서/회의/결정을 종합해서 근거 기반 답변을 만드는 작업이라 Model1(가벼움)보다
#   Model2(qwen3:8b, post-meeting 요약에 쓰는 것과 동일)가 적합하다고 판단.
# - _call_ollama()를 거치면 다른 노드들과 동일하게 중국어 감지 자동 재시도가 적용된다
#   (기존엔 httpx.post 직접 호출이라 이 안전장치가 빠져있었음).
CHAT_ANSWER_MODEL = OLLAMA_MODEL_HEAVY

TOP_K_PER_COLLECTION = 5
# [수정] 컬렉션별 최소 보장(MIN_PER_COLLECTION)을 도입하면서 5 → 6으로 올렸다.
# 컬렉션이 3개라 2개씩 보장하려면 최소 6칸이 필요하다(5로 두면 보장 자체가 성립 안 함).
TOP_K_FINAL = 6
# 한 컬렉션이 상위 점수를 독식해도 나머지 컬렉션 후보가 최소 이만큼은 살아남는다.
# 같은 문서 안의 다른 섹션(예: 배포일정 vs 코드리뷰 규칙)이 다른 컬렉션 후보에
# 밀려 통째로 누락되던 문제 때문에 추가 (지수 리포트).
MIN_PER_COLLECTION = 2
CHAT_HISTORY_TURNS = 3
# rag_service.py의 실측 기준 주석("8개 질문 실측: 관련있음 0.6~0.99, 무관 0.4 미만")과
# 동일한 임계값 사용 — ChromaDB는 컬렉션에 데이터가 있으면 관련성과 무관하게
# 최근접 결과를 반환하므로, 이 이상인 결과만 실제 근거로 취급한다.
#
# [중요 - 수정] 이 0.4는 rag_service.py에서 "리랭커 점수" 분포를 보고 정한 값인데,
# 예전엔 리랭킹을 거치지 않은 raw 하이브리드 점수(semantic*0.7 + BM25*0.3)에
# 그대로 적용하고 있었다. 서로 다른 척도라 오탐/누락이 났다 — 특히 오타가 있으면
# BM25 항이 0이 되어 점수 상한이 0.7로 떨어지고, 정답 청크가 1위인데도 임계값을
# 못 넘어 결과가 통째로 비는 현상이 있었다(지수 리포트: "베포" → "배포").
# 이제 rerank_results()를 거친 뒤 reranker_score에 적용하므로 척도가 일치한다.
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
자연스러운 한국어 문장으로 답하세요 (JSON이나 마크다운 형식 없이 답변 텍스트만).

답변을 마친 뒤 마지막 줄에, 실제로 답변 작성에 사용한 근거 자료의 번호만 아래 형식 그대로 적으세요.
사용한 근거가 없으면 이 줄은 생략하세요.
[출처: 1,3]"""

# 답변 맨 끝에 붙는 [출처: 1,3] 형태의 인용 마커를 잡아낸다. 답변 텍스트 안쪽에
# 우연히 비슷한 패턴이 나와도 잘못 지우지 않도록, 문자열 맨 끝(공백 허용)에서만 매치한다.
# [수정] 괄호 안 내용을 숫자/쉼표/공백으로만 한정하면(예: [0-9,\s]*), 모델이 형식을
# 살짝 어겨서 "[출처: a,b]"처럼 글자가 섞인 걸 내놓을 때 정규식 자체가 매치를 못 해서
# 마커 텍스트가 그대로 사용자 답변에 노출된다. 괄호 안은 뭐든 일단 잡아내고(.*?),
# 숫자만 골라내는 건 파이썬 쪽(_parse_cited_indices)에서 따로 검증한다 - 그래야
# 마커 모양만 맞으면 내용이 이상해도 항상 화면에서는 지워진다.
_SOURCE_CITATION_PATTERN = re.compile(r"\[출처:\s*(.*?)\]\s*$")


def candidate_score(candidate: dict) -> float:
    """랭킹/필터링에 쓸 점수를 꺼낸다.

    rerank_results()를 거친 뒤에는 reranker_score가 채워져 있으므로 그것을 쓰고,
    아직 안 거쳤거나 리랭커가 실패해 폴백된 경우엔 하이브리드 score로 떨어진다.
    (rerank_results는 실패 시 reranker_score = score로 채워주므로 두 경우 모두 안전)
    """
    return candidate.get("reranker_score", candidate.get("score", 0.0))


def merge_and_rank_candidates(
    doc_results: list[dict],
    meeting_results: list[dict],
    decision_results: list[dict] | None = None,
    top_k: int = TOP_K_FINAL,
    min_per_collection: int = MIN_PER_COLLECTION,
) -> list[dict]:
    """문서/회의/결정사항 검색 결과를 병합해 최종 top_k개를 고른다.

    search_hybrid()는 collection_name에 컬렉션 하나만 받을 수 있어
    문서/회의/결정사항을 각각 따로 검색한 뒤 여기서 합친다.
    decision_results는 선택값 — 생략하면 기존 문서/회의 2종 병합과 동일하게 동작한다.

    [수정] 단순 점수순 상위 top_k 절단에서, 컬렉션별 최소 개수를 먼저 보장한 뒤
    남은 자리를 점수순으로 채우는 방식으로 변경했다 (지수 리포트).
    기존 방식은 한 컬렉션이 상위 점수를 독식하면 다른 컬렉션 후보가 필터링 전에
    통째로 잘려나가서, 같은 문서의 다른 섹션이 답변 근거에서 누락되는 문제가 있었다.

    min_per_collection * 컬렉션수가 top_k보다 크면 보장을 다 채울 수 없으므로,
    각 컬렉션에서 라운드로빈으로 한 개씩 뽑아 top_k까지만 채운다(균등 분배).
    """
    per_collection = [list(doc_results), list(meeting_results), list(decision_results or [])]
    for results in per_collection:
        results.sort(key=candidate_score, reverse=True)

    selected: list[dict] = []
    selected_ids: set[int] = set()

    def take(candidate: dict) -> None:
        selected.append(candidate)
        selected_ids.add(id(candidate))

    # 1단계: 컬렉션별 최소 보장. 라운드로빈으로 돌면서 뽑아, 자리가 모자라도
    # 특정 컬렉션만 몰아서 채워지지 않게 한다.
    for rank in range(max(min_per_collection, 0)):
        for results in per_collection:
            if len(selected) >= top_k:
                break
            if rank < len(results):
                take(results[rank])
        if len(selected) >= top_k:
            break

    # 2단계: 남은 자리는 컬렉션 구분 없이 점수순으로 채운다.
    remaining = [
        c for results in per_collection for c in results if id(c) not in selected_ids
    ]
    remaining.sort(key=candidate_score, reverse=True)
    selected.extend(remaining[: max(top_k - len(selected), 0)])

    # 최종 결과는 점수순으로 정렬해서 돌려준다 (프롬프트에 근거를 넣는 순서 =
    # 관련도 순서가 되도록). 보장 단계에서 섞인 순서를 여기서 다시 정리한다.
    selected.sort(key=candidate_score, reverse=True)
    return selected


def filter_by_relevance(candidates: list[dict], min_score: float = MIN_RELEVANCE_SCORE) -> list[dict]:
    """검색 점수가 임계값 미만인 후보를 제거한다.

    ChromaDB는 컬렉션에 데이터가 있기만 하면 질문과 무관해도 "가장 가까운" 결과를
    반환하므로, 임계값 없이는 NO_RESULTS_ANSWER가 사실상 컬렉션이 완전히 비어있을
    때만 동작하게 된다.

    [수정] 비교 대상을 raw 하이브리드 score에서 candidate_score()(리랭킹 후에는
    reranker_score)로 바꿨다 — MIN_RELEVANCE_SCORE가 원래 리랭커 점수 기준으로
    측정된 값이라 척도를 맞추기 위함.
    """
    return [c for c in candidates if candidate_score(c) >= min_score]


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
    """검색된 청크 본문 + 대화 이력 + 질문을 하나의 프롬프트로 조립한다.

    [수정] 근거 자료에 [1] [2] [3]처럼 번호를 매겨서 넣는다 - LLM이 실제로 답변에
    쓴 근거만 응답 끝에 [출처: 1,3] 형식으로 표시하게 하기 위함(승주 요청).
    번호는 1부터 시작하고, context_texts의 순서(=ai_chat_answer_node의 resolved
    순서)와 1:1 대응한다. _parse_cited_indices()가 이 번호를 그대로 되읽는다.
    """
    if context_texts:
        context = "\n\n---\n\n".join(f"[{i}] {text}" for i, text in enumerate(context_texts, start=1))
    else:
        context = "(근거 자료 없음)"
    history = format_chat_history(chat_history)
    return _ANSWER_PROMPT.format(context=context, history=history, question=question)


def _parse_cited_indices(answer: str) -> tuple[str, set[int] | None]:
    """LLM 답변 끝에 붙은 [출처: 1,3] 마커를 파싱한다.

    Returns:
        (마커를 제거한 답변 텍스트, 인용된 1-based 번호 집합)
        마커가 아예 없거나, 있어도 숫자를 하나도 못 뽑아냈으면(형식이 깨진 경우)
        두 번째 값으로 None을 반환한다. 호출부는 None이면 기존 동작(전체 표시)으로
        안전하게 폴백해야 한다 - 인용 파싱 때문에 근거가 통째로 안 보이는 회귀를
        만들면 안 된다는 게 이 기능의 전제 조건.
    """
    stripped = answer.rstrip()
    match = _SOURCE_CITATION_PATTERN.search(stripped)
    if not match:
        return answer, None

    clean_answer = stripped[: match.start()].rstrip()

    indices: set[int] = set()
    for part in match.group(1).split(","):
        part = part.strip()
        if part.isdigit():
            indices.add(int(part))

    if not indices:
        # 마커는 있는데 숫자를 하나도 못 읽음(예: "[출처: ]", "[출처: a,b]") - 폴백.
        # 그래도 마커 텍스트 자체는 사용자에게 안 보이는 게 맞으므로 clean_answer는 유지.
        return clean_answer, None

    return clean_answer, indices


def _call_llm_answer(prompt: str) -> str | None:
    """Ollama에 일반 텍스트 답변 생성을 요청한다. 실패 시 None (다른 노드처럼 JSON 강제 안 함 — 채팅 답변은 텍스트 그대로 노출).

    공용 _call_ollama()를 거치므로 중국어 감지 시 자동 재시도(최대 2회)가 적용된다.
    """
    try:
        answer = _call_ollama(prompt, timeout=120.0, model=CHAT_ANSWER_MODEL).strip()
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

    # [수정] 컬렉션별 후보 확보 → 리랭킹 → 최종 슬라이싱 순서.
    # 리랭킹을 최종 슬라이싱보다 먼저 해야, 하이브리드 점수 기준으로 잘려나간 뒤
    # 남은 것만 리랭킹하는 상황(=리랭커가 볼 후보 자체가 이미 편향됨)을 피할 수 있다.
    # rerank_results()는 reranker_score만 채우고 정렬은 하지 않으므로, 정렬/슬라이싱은
    # merge_and_rank_candidates()가 담당한다.
    for results in (doc_results, meeting_results, decision_results):
        if results:
            rerank_results(user_message, results)

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
                    # [참고 - 지수 리뷰] Decision 모델엔 category_id 컬럼이 없어서
                    # content_chunk처럼 Postgres에서 2차 category 검증을 할 수 없다.
                    # category 스코핑은 search_hybrid() 호출 시 Chroma where 필터
                    # 하나에만 의존한다 - indexer.index_decisions()가 category_id를
                    # 정확히 넣고 있어서 지금은 안전하지만, MVP가 워크스페이스당
                    # 카테고리 1개뿐이라 실질적 위험이 낮은 것도 있다. 카테고리가
                    # 여러 개로 늘어나면 Decision에 category_id 컬럼 추가를 재검토할 것.
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

    # [수정] LLM이 답변 끝에 붙인 [출처: 1,3] 마커로, 실제로 인용한 근거만 sources에
    # 남긴다 (승주 요청). MIN_PER_COLLECTION 보장 때문에 낮은 점수로 억지로 끼워진
    # 후보까지 근거자료로 노출되던 문제. 마커가 없거나 파싱이 이상하면(모델이 형식을
    # 안 지킨 경우) cited_indices가 None이 되고, 그러면 기존처럼 전체를 보여준다 —
    # 인용 파싱 때문에 근거가 통째로 안 보이는 회귀는 절대 만들지 않는다.
    answer, cited_indices = _parse_cited_indices(answer)

    sources = []
    for i, (candidate, kind, obj) in enumerate(resolved):
        if cited_indices is not None and (i + 1) not in cited_indices:
            continue

        # [수정] 저장하는 유사도도 실제 선별 기준이 된 점수(리랭킹 후 reranker_score)로
        # 맞춘다. 예전엔 raw 하이브리드 score를 저장해서, 근거가 뽑힌 이유와 화면에
        # 표시되는 유사도가 서로 다른 값이었다.
        score = clamp_similarity_score(candidate_score(candidate))
        # display_order는 필터링 후 순서로 다시 매긴다 (건너뛴 항목 때문에 번호가
        # 듬성듬성해지지 않도록).
        if kind == "decision":
            sources.append({
                "source_type": "decision",
                "decision_id": obj.id,
                "similarity_score": score,
                "display_order": len(sources),
            })
        else:
            sources.append({
                "source_type": "content_chunk",
                "file_id": obj.file_id,
                "chunk_id": obj.id,
                "similarity_score": score,
                "display_order": len(sources),
            })

    return {
        "answer": answer,
        "answer_model_name": CHAT_ANSWER_MODEL,
        "chunk_search_results": candidates,
        "retrieved_sources": sources,
    }
