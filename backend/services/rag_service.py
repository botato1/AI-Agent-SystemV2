# backend/services/rag_service.py
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from backend.modules.rag.chroma_client import (
    search_hybrid,
    rerank_results,
    MEETING_COLLECTION,
    DOCUMENT_COLLECTION,
    KNOWLEDGE_COLLECTION,
    CONTEXT_TO_COLLECTION,
)

# TODO: room 기반 문서 조회는 legacy 개념. AI Chat 그래프(ai_chat_state.py) 노드
# 구현 시 workspace_id/category_id 기준 content_chunk_crud로 교체해야 한다.
# 지금은 import 에러만 막아두는 임시 스텁이며 실제 호출 시 의도적으로 실패한다.
def get_documents_by_room_id(room_id: str) -> list:
    raise NotImplementedError("get_documents_by_room_id는 아직 새 도메인으로 마이그레이션되지 않았습니다.")


def get_document_by_title_and_room(room_id: str, title: str) -> dict | None:
    raise NotImplementedError("get_document_by_title_and_room은 아직 새 도메인으로 마이그레이션되지 않았습니다.")


# ── 상수 ─────────────────────────────────────────────────────
CANDIDATE_K  = 40
SCALE_FACTOR = 0.0005

# 8개 질문 실측 기준: 관련있음 0.6~0.99, 무관 0.4 미만
LOW_CONFIDENCE_THRESHOLD = 0.4

MEETING_SIGNALS = [
    "회의록", "회의", "저번에", "저번", "말했던", "논의했던", "논의",
    "액션아이템", "참석자", "지난번", "지난", "미팅",
    "담당자", "담당", "할일", "할 일", "누구", "마감",
    "스프린트", "배포 담당",
]
DOCUMENT_SIGNALS = [
    "문서", "파일", "보냈던", "올린", "자료",
    "보고서", "pdf", "첨부", "요약", "정리",
]
KNOWLEDGE_SIGNALS = [
    # 일반 기술 키워드
    "에러", "오류", "방법", "설치", "설정", "코드", "구현", "사용",
    "배포", "파이프라인", "빌드", "실행", "연결", "적용", "구성",
    # 도커
    "도커", "docker", "dockerfile", "컨테이너", "container",
    "이미지", "image", "compose", "레지스트리",
    # 쿠버네티스
    "쿠버", "kubernetes", "k8s", "pod", "파드", "deployment",
    "서비스", "ingress", "helm", "클러스터", "노드",
    # 깃허브
    "깃허브", "github", "actions", "워크플로", "workflow",
    "ci", "cd", "cicd", "브랜치", "커밋", "push", "pull request",
    # 기타 기술
    "api", "서버", "네트워크", "network", "포트", "port",
    "데이터베이스", "db", "sql", "redis", "nginx",
    "로그", "모니터링", "장애", "디버그", "테스트",
]

# 컬렉션 이름 → 결과 키 매핑
COL_KEY_MAP = {
    MEETING_COLLECTION:   "meeting",
    DOCUMENT_COLLECTION:  "document",
    KNOWLEDGE_COLLECTION: "knowledge",
}


def get_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _resolve_filter(filter: dict | None) -> dict | None:
    """
    document_ids 배열이 들어오면 ChromaDB가 이해하는 $in 형식으로 변환.
    단일 문서일 때만 사용. 다중 문서는 _search_multi_documents()로 분리 검색.
    """
    if not filter:
        return filter
    document_ids = filter.get("document_ids")
    if document_ids and isinstance(document_ids, list):
        print(f"[RAG Service] document_ids 배열 감지 → $in 필터로 변환: {document_ids}")
        resolved = {k: v for k, v in filter.items() if k != "document_ids"}
        resolved["document_id"] = {"$in": document_ids}
        return resolved
    return filter


def _search_multi_documents(query: str, document_ids: list[str], top_k: int) -> dict:
    """
    [수정 - 다중 문서 결과 쏠림 해결]
    기존: document_ids를 $in으로 한 번에 검색 → score 높은 chunk 순서로 잘려서
         특정 문서 chunk가 score 우위면 다른 문서가 거의 안 잡히는 쏠림 발생.
    변경: 문서별로 따로 검색해서 문서당 결과를 보장한 뒤 합친다.
         문서 N개면 문서당 top_k // N개씩 (최소 1개) 확보.

    document_collection / meeting_collection 둘 다 대상이 될 수 있으므로
    컬렉션 무관하게 document_id 단일 필터로 각각 검색.
    """
    n = len(document_ids)
    if n == 0:
        return _empty_collection_result()

    per_doc_k = max(1, top_k // n)
    all_formatted = []

    for doc_id in document_ids:
        for col in [MEETING_COLLECTION, DOCUMENT_COLLECTION]:
            raw = search_hybrid(
                query_text=query,
                top_k=CANDIDATE_K,
                filter={"document_id": doc_id},
                collection_name=col,
            )
            if not raw:
                continue
            raw = rerank_results(query, raw)
            raw = _apply_final_score(raw)
            formatted = _format_documents(raw)
            # 문서별 top-k만 보장해서 추가 (전체를 합치기 전에 문서 단위로 자름)
            all_formatted.extend(formatted[:per_doc_k])
            print(f"[RAG Service] document_id={doc_id} ({col}) → {len(formatted[:per_doc_k])}개 확보")

    if not all_formatted:
        return _empty_collection_result()

    all_formatted.sort(key=lambda x: x["score"], reverse=True)
    return _make_collection_result_skip(all_formatted, top_k=top_k, skip_threshold=True)

def _has_specific_document_filter(filter: dict | None) -> bool:
    if not filter:
        return False
    return bool(filter.get("document_id") or filter.get("filename"))


def _refine_query_for_knowledge(query: str) -> str:
    """
    knowledge_collection 검색용 쿼리 정제.
    회의/문서 관련 맥락 표현을 정규식 패턴으로 제거해서 기술 내용만 남긴다.

    예: "저번 회의에서 나온 에러 해결방안 알려줘" -> "에러 해결방안 알려줘"
    예: "저번 미팅에서 논의한 쿠버네티스 배포 문제" -> "쿠버네티스 배포 문제"

    접근: MEETING_SIGNALS/DOCUMENT_SIGNALS를 단순 제거하는 대신,
    "회의/미팅/저번 + 조사/어미" 패턴을 한 덩어리로 잡아서 제거.
    이 방식이 "한", "된" 같은 어미 찌꺼기를 남기지 않아 더 안전함.

    제거 후 결과가 너무 짧아지면(5글자 미만) 원문을 그대로 반환한다.
    """
    # 회의 맥락 패턴: "저번/지난 + (회의/미팅 등) + 조사어미" 형태를 통째로 제거
    # 각 패턴을 명시적으로 정의 (과잉 제거 방지)
    meeting_patterns = [
        r"저번\s*(?:회의록?|미팅|번|에)?\s*(?:에서|에서의|의|에게|때|으로부터|로부터)?",
        r"지난\s*(?:번|회의록?|미팅|번의)?\s*(?:에서|에서의|의|에게|때|으로부터|로부터)?",
        r"(?:회의록?|미팅)\s*(?:에서|에서의|에|의|때|에서도|에서부터)?",
        r"(?:논의|말|얘기)(?:했던|한|된|할)\s*",
        r"액션\s*아이템\s*",
        r"참석자\s*(?:들?의|들?)?\s*",
    ]
    document_patterns = [
        r"(?:문서|파일|자료|보고서|첨부)\s*(?:에서|에서의|에|의|를|을|로|으로)?",
        r"(?:보냈던|올린|올렸던)\s*",
        r"pdf\s*(?:에서|에서의|에|의|를|을)?",
    ]

    refined = query
    for pattern in meeting_patterns + document_patterns:
        refined = re.sub(pattern, " ", refined, flags=re.IGNORECASE)

    refined = re.sub(r"\s+", " ", refined).strip()

    if len(refined) < 5:
        return query
    return refined


def _select_collections_with_queries(
    question_type: str,
    query: str = "",
    filter: dict | None = None,
) -> list[tuple[str, str]]:
    """
    검색할 컬렉션과 그 컬렉션에 맞는 정제된 쿼리를 함께 반환한다.
    반환 형식: [(collection_name, query_for_this_collection), ...]

    컬렉션별 쿼리 정제 규칙:
    - meeting_collection  -> 원문 그대로 (회의 맥락 단어가 오히려 도움)
    - document_collection -> 원문 그대로 (사용자가 직접 가리킨 문서)
    - knowledge_collection -> MEETING_SIGNALS/DOCUMENT_SIGNALS 제거
                              (기술 내용만 남겨서 임베딩 정확도 향상)

    예: "저번 회의에서 나온 에러 해결방안 알려줘"
        meeting_collection   -> "저번 회의에서 나온 에러 해결방안 알려줘" (원문)
        knowledge_collection -> "에러 해결방안 알려줘" (정제)
    """
    all_collections = [MEETING_COLLECTION, DOCUMENT_COLLECTION, KNOWLEDGE_COLLECTION]

    if _has_specific_document_filter(filter):
        return [(col, query) for col in all_collections]

    has_meeting   = any(s in query for s in MEETING_SIGNALS)
    has_document  = any(s in query for s in DOCUMENT_SIGNALS)
    has_knowledge = any(s in query for s in KNOWLEDGE_SIGNALS)

    targets = set()
    if has_meeting:   targets.add(MEETING_COLLECTION)
    if has_document:  targets.add(DOCUMENT_COLLECTION)
    if has_knowledge: targets.add(KNOWLEDGE_COLLECTION)

    if question_type == "task_from_rag":
        targets.add(MEETING_COLLECTION)

    if not targets:
        targets = set(all_collections)

    knowledge_query = _refine_query_for_knowledge(query)

    result = []
    for col in targets:
        if col == KNOWLEDGE_COLLECTION:
            result.append((col, knowledge_query))
        else:
            result.append((col, query))

    return result


def _select_collections(
    question_type: str,
    query: str = "",
    filter: dict | None = None,
) -> list[str]:
    """하위 호환성 유지용. 컬렉션 이름만 반환."""
    return [col for col, _ in _select_collections_with_queries(
        question_type=question_type,
        query=query,
        filter=filter,
    )]


def _apply_final_score(results: list) -> list:
    """reranker_score + tech_score 보정 → final_score 계산 후 정렬."""
    for res in results:
        reranker_score = res.get("reranker_score", 0.0)
        if res.get("collection") == KNOWLEDGE_COLLECTION:
            tech_score = res.get("metadata", {}).get("tech_score", 0)
            res["final_score"] = reranker_score + tech_score * SCALE_FACTOR
        else:
            res["final_score"] = reranker_score

    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results


def _format_documents(raw_results: list) -> list:
    """raw_results → 최종 반환 포맷으로 변환."""
    processed = []
    for res in raw_results:
        meta = res.get("metadata", {})
        processed.append({
            "id":             res.get("id", ""),
            "content":        res.get("content") or res.get("document", ""),
            "title":          meta.get("title", "제목 없음"),
            "type":           meta.get("type", "document"),
            "source":         meta.get("source", ""),
            "language":       meta.get("language", "ko"),
            "created_at":     meta.get("created_at", get_utc_now()),
            "status":         meta.get("status", "processed"),
            "chroma_id":      meta.get("chroma_id", ""),
            "error":          meta.get("error", ""),
            "user_edited":    meta.get("user_edited", False),
            "tags":           meta.get("tags", ""),
            "importance_score": meta.get("importance_score", 0),
            "score":          res.get("final_score", 0),
            "reranker_score": res.get("reranker_score", 0),
            "tech_score":     meta.get("tech_score", 0),
            "document_id":    meta.get("document_id", ""),
            "filename":       meta.get("filename", ""),
            "chunk_index":    meta.get("chunk_index", 0),
            "upload_context": meta.get("upload_context", ""),
            "room_id":        meta.get("room_id", ""),
            "collection":     res.get("collection", ""),
        })
    return processed


def _make_collection_result(documents: list, top_k: int) -> dict:
    """단일 컬렉션의 처리 결과를 신뢰도 포함해서 반환."""
    sliced = documents[:top_k]
    top_score = sliced[0]["score"] if sliced else 0.0
    return {
        "count": len(sliced),
        "low_confidence": top_score < LOW_CONFIDENCE_THRESHOLD,
        "top_score": round(top_score, 4),
        "data": sliced,
    }


def _empty_collection_result() -> dict:
    return {"count": 0, "low_confidence": True, "top_score": 0.0, "data": []}


def _is_room_query(query: str) -> bool:
    q = query.lower()
    return any(s in q for s in MEETING_SIGNALS + DOCUMENT_SIGNALS)


def _make_collection_result_skip(documents: list, top_k: int, skip_threshold: bool = False) -> dict:
    sliced = documents[:top_k]
    top_score = sliced[0]["score"] if sliced else 0.0
    return {
        "count": len(sliced),
        "low_confidence": False if skip_threshold else top_score < LOW_CONFIDENCE_THRESHOLD,
        "top_score": round(top_score, 4),
        "data": sliced,
    }


def _search_and_rerank(query: str, collection_name: str, filter_dict, skip_threshold: bool = False) -> dict:
    raw = search_hybrid(query_text=query, top_k=CANDIDATE_K, filter=filter_dict, collection_name=collection_name)
    if not raw:
        return _empty_collection_result()
    raw = rerank_results(query, raw)
    raw = _apply_final_score(raw)
    formatted = _format_documents(raw)
    return _make_collection_result_skip(formatted, top_k=5, skip_threshold=skip_threshold)


def _search_room_docs(query: str, room_docs: list, collection_results: dict, skip_threshold: bool = False):
    meeting_ids = [d["id"] for d in room_docs if d.get("type") in ("voice", "meeting")]
    document_ids = [d["id"] for d in room_docs if d.get("type") == "document"]

    if meeting_ids:
        f = {"document_id": {"$in": meeting_ids}} if len(meeting_ids) > 1 else {"document_id": meeting_ids[0]}
        collection_results["meeting"] = _search_and_rerank(query, MEETING_COLLECTION, f, skip_threshold)

    if document_ids:
        f = {"document_id": {"$in": document_ids}} if len(document_ids) > 1 else {"document_id": document_ids[0]}
        collection_results["document"] = _search_and_rerank(query, DOCUMENT_COLLECTION, f, skip_threshold)


def _build_empty_result(query: str, collection_results: dict) -> dict:
    return {
        "status": "success",
        "query": query,
        "count": 0,
        "data": [],
        "low_confidence": True,
        "collection_results": collection_results,
        "searched_collections": [],
        "error": None,
    }


class RAGService:

    @staticmethod
    def retrieve_relevant_knowledge(
        query: str,
        original_query: str = None,
        top_k: int = 5,
        relative_threshold: float = 0.5,
        filter: dict = None,
        question_type: str = "general_answer",
        room_id: str = "",
    ):
        print(f"[RAG Service] 쿼리: '{query}' / 타입: '{question_type}'")
        print(f"[RAG Service] room_id: {room_id}, filter: {filter}")

        try:
            collection_results = {
                "meeting": _empty_collection_result(),
                "document": _empty_collection_result(),
                "knowledge": _empty_collection_result(),
            }

            # ── 다중 문서 선택 (document_ids 2개 이상) ──────────────
            # $in으로 한 번에 검색하면 score 쏠림이 생기므로 문서별로 분리 검색
            raw_document_ids = filter.get("document_ids") if filter else None
            is_multi_doc = bool(raw_document_ids and isinstance(raw_document_ids, list) and len(raw_document_ids) > 1)

            if not is_multi_doc:
                # 단일 문서(또는 document_ids 1개) / 일반 filter: $in 변환
                filter = _resolve_filter(filter)

            if is_multi_doc:
                print(f"[RAG Service] 다중 문서 분리 검색: {raw_document_ids}")
                multi_result = _search_multi_documents(query, raw_document_ids, top_k=top_k)
                collection_results["document"] = multi_result

            elif question_type in ("task_from_rag", "summary_from_rag") and room_id:
                room_docs = get_documents_by_room_id(room_id)
                print(f"[RAG Service] room_docs: {room_docs}")
                if not room_docs:
                    print(f"[RAG Service] room_id={room_id} 에 문서 없음")
                    return _build_empty_result(query, collection_results)

                target_docs = room_docs
                for doc in room_docs:
                    title = doc.get("title", "")
                    clean_title = title.replace(".pdf", "").replace(".docx", "").replace(".md", "")
                    if clean_title and clean_title in query:
                        target_docs = [doc]
                        print(f"[RAG Service] 특정 문서 감지: {title}")
                        break

                _search_room_docs(query, target_docs, collection_results, skip_threshold=True)

            # ── knowledge_search ──
            elif question_type == "knowledge_search":
                if room_id and _is_room_query(query):
                    room_docs = get_documents_by_room_id(room_id)
                    if room_docs:
                        _search_room_docs(query, room_docs, collection_results)
                    else:
                        print(f"[RAG Service] room_id={room_id} 에 문서 없음 → knowledge 검색")
                        collection_results["knowledge"] = _search_and_rerank(query, KNOWLEDGE_COLLECTION, None)
                elif filter:
                    # filter 기반 기존 방식
                    collections_with_queries = _select_collections_with_queries(
                        question_type=question_type, query=query, filter=filter,
                    )
                    collections = [col for col, _ in collections_with_queries]
                    per_col: dict[str, list] = {"meeting": [], "document": [], "knowledge": []}
                    seen_ids: set = set()
                    for col, col_query in collections_with_queries:
                        raw = search_hybrid(query_text=col_query, top_k=CANDIDATE_K, filter=filter, collection_name=col)
                        unique = [r for r in raw if r["id"] not in seen_ids]
                        for r in unique:
                            seen_ids.add(r["id"])
                        if not unique:
                            continue
                        unique = rerank_results(query, unique)
                        unique = _apply_final_score(unique)
                        formatted = _format_documents(unique)
                        key = COL_KEY_MAP.get(col, "knowledge")
                        per_col[key].extend(formatted)
                    collection_results = {
                        key: (_make_collection_result(per_col[key], top_k) if per_col[key] else _empty_collection_result())
                        for key in ["meeting", "document", "knowledge"]
                    }
                else:
                    collection_results["knowledge"] = _search_and_rerank(query, KNOWLEDGE_COLLECTION, None)

            # ── 기타 (filter 기반 기존 방식) ──
            else:
                if filter:
                    collections_with_queries = _select_collections_with_queries(
                        question_type=question_type, query=query, filter=filter,
                    )
                    per_col: dict[str, list] = {"meeting": [], "document": [], "knowledge": []}
                    seen_ids: set = set()
                    for col, col_query in collections_with_queries:
                        raw = search_hybrid(query_text=col_query, top_k=CANDIDATE_K, filter=filter, collection_name=col)
                        unique = [r for r in raw if r["id"] not in seen_ids]
                        for r in unique:
                            seen_ids.add(r["id"])
                        if not unique:
                            continue
                        unique = rerank_results(query, unique)
                        unique = _apply_final_score(unique)
                        formatted = _format_documents(unique)
                        key = COL_KEY_MAP.get(col, "knowledge")
                        per_col[key].extend(formatted)
                    collection_results = {
                        key: (_make_collection_result(per_col[key], top_k) if per_col[key] else _empty_collection_result())
                        for key in ["meeting", "document", "knowledge"]
                    }

            # ── 전체 합산 ──
            all_docs = []
            for key in ["meeting", "document", "knowledge"]:
                all_docs.extend(collection_results[key].get("data", []))

            if not all_docs:
                return _build_empty_result(query, collection_results)

            all_docs.sort(key=lambda x: x["score"], reverse=True)
            top_documents = all_docs[:top_k]
            top_score = top_documents[0]["score"] if top_documents else 0

            any_skip = any(
                not v.get("low_confidence", True)
                for v in collection_results.values()
                if v.get("count", 0) > 0
            )
            is_low_confidence = False if any_skip else top_score < LOW_CONFIDENCE_THRESHOLD

            cr = collection_results
            print(
                f"[RAG Service] 완료 → {len(top_documents)}개 반환 "
                f"(최고 score: {top_score:.4f}, 신뢰도: {'낮음' if is_low_confidence else '정상'})"
            )
            print(
                f"[RAG Service] 컬렉션별 → "
                f"meeting={cr['meeting']['count']}개"
                f"({'낮음' if cr['meeting']['low_confidence'] else '정상'}), "
                f"document={cr['document']['count']}개"
                f"({'낮음' if cr['document']['low_confidence'] else '정상'}), "
                f"knowledge={cr['knowledge']['count']}개"
                f"({'낮음' if cr['knowledge']['low_confidence'] else '정상'})"
            )

            return {
                "status": "success",
                "query":  query,
                "count":  len(top_documents),
                "data":   top_documents,
                "low_confidence": is_low_confidence,
                "collection_results": collection_results,
                "searched_collections": [k for k, v in collection_results.items() if v["count"] > 0],
                "error":  None,
            }

        except Exception as e:
            print(f"[RAG Service 에러]: {str(e)}")
            empty = _empty_collection_result()
            return {
                "status": "error",
                "query":  query,
                "count":  0,
                "data":   [],
                "low_confidence": True,
                "collection_results": {
                    "meeting": empty, "document": empty, "knowledge": empty,
                },
                "error": f"RAG 파이프라인 장애: {str(e)}",
            }

    @staticmethod
    def retrieve_relevant_knowledge_sync(
        query: str,
        original_query: str = None,
        top_k: int = 5,
        relative_threshold: float = 0.5,
        filter: dict = None,
        question_type: str = "general_answer",
        room_id: str = "",
    ) -> dict:
        return RAGService.retrieve_relevant_knowledge(
            query=query,
            original_query=original_query,
            top_k=top_k,
            relative_threshold=relative_threshold,
            filter=filter,
            question_type=question_type,
            room_id=room_id,
        )


rag_service = RAGService()