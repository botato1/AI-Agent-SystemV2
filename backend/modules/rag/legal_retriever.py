# backend/modules/rag/legal_retriever.py
#
# 법률 AI 어시스턴트 v2 — RAG 검색 모듈
#
# [컬렉션 구조]
#   legal_corpus   : 법조문(doc_category=statute) + 판례(doc_category=precedent)
#   user_documents : 사용자 업로드 문서 (계약서/증거서류/상담메모 등)
#
# [검색 전략]
#   1. 하이브리드 검색 (BGE-M3 벡터 + BM25 키워드)
#   2. 리랭킹 (BAAI/bge-reranker-v2-m3)
#   3. 판례 sibling 청크 묶기 (같은 판례번호의 핵심 섹션 자동 추가)
#   4. needs_more_context 신호 (판례 전문 추가 여부 판단)
#
# [intent별 검색 대상]
#   contract_risk_check : legal_corpus + user_documents
#   statute_search      : legal_corpus (doc_category=statute만)
#   precedent_search    : legal_corpus (doc_category=precedent만)
#   legal_search        : legal_corpus 전체
#   general_answer      : 검색 없음
import os
import sys
import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

BASE_DIR = Path(__file__).resolve().parents[3]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import torch        # noqa: F401
import pandas       # noqa: F401
import sklearn      # noqa: F401
import transformers # noqa: F401
import datasets     # noqa: F401

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# ── 경로 설정 ─────────────────────────────────────────────────
CHROMA_DIR = "./storage/chroma"
BM25_DIR   = "./storage/bm25"
os.makedirs(BM25_DIR, exist_ok=True)

# ── 컬렉션 이름 상수 ──────────────────────────────────────────
LEGAL_CORPUS    = "legal_corpus"     # 법조문 + 판례
USER_DOCUMENTS  = "user_documents"   # 사용자 업로드 문서

# ── 검색 파라미터 ─────────────────────────────────────────────
CANDIDATE_K         = 60     # 1차 검색 후보 수
FINAL_K             = 5      # 리랭킹 후 최종 반환 수
VECTOR_WEIGHT       = 0.7    # 벡터 검색 가중치
BM25_WEIGHT         = 0.3    # BM25 키워드 검색 가중치
CONFIDENCE_THRESHOLD = 0.4   # needs_more_context 판단 기준

# 판례 핵심 섹션 (항상 같이 가져오는 것)
CORE_SECTIONS = ["판시사항", "판결요지", "참조조문", "참조판례"]


# ── ChromaDB 클라이언트 ───────────────────────────────────────
_chroma_client = None

def _get_chroma_client():
    # 캐싱 제거, 매번 새로 생성
    return chromadb.PersistentClient(path=CHROMA_DIR)


def _get_collection(collection_name: str):
    ef = SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-m3")
    return chromadb.PersistentClient(path=CHROMA_DIR).get_collection(
        name=collection_name,
        embedding_function=ef,
    )

# ── BM25 인덱스 관리 ──────────────────────────────────────────
def _bm25_path(collection_name: str) -> str:
    return os.path.join(BM25_DIR, f"{collection_name}.pkl")


def _load_bm25_index(collection_name: str) -> dict:
    path = _bm25_path(collection_name)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return {"doc_ids": [], "tokenized_docs": []}


def _save_bm25_index(collection_name: str, index_data: dict):
    with open(_bm25_path(collection_name), "wb") as f:
        pickle.dump(index_data, f)


def _build_bm25(tokenized_docs: list) -> BM25Okapi:
    if not tokenized_docs:
        return BM25Okapi([[""]])
    return BM25Okapi(tokenized_docs)


def update_bm25_index(collection_name: str, doc_id: str, document: str):
    """문서 적재 시 BM25 인덱스 업데이트 (law_loader.py에서 호출)"""
    index_data = _load_bm25_index(collection_name)
    if doc_id not in index_data["doc_ids"]:
        index_data["doc_ids"].append(doc_id)
        index_data["tokenized_docs"].append(document.split())
        _save_bm25_index(collection_name, index_data)


def remove_from_bm25_index(collection_name: str, doc_id: str):
    """문서 삭제 시 BM25 인덱스에서 제거"""
    index_data = _load_bm25_index(collection_name)
    if doc_id in index_data["doc_ids"]:
        idx = index_data["doc_ids"].index(doc_id)
        index_data["doc_ids"].pop(idx)
        index_data["tokenized_docs"].pop(idx)
        _save_bm25_index(collection_name, index_data)


# ── Reranker ─────────────────────────────────────────────────
_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None:
        from FlagEmbedding import FlagReranker
        print("[reranker] BAAI/bge-reranker-v2-m3 로딩 중 (GPU, fp16)...")
        _reranker = FlagReranker(
            "BAAI/bge-reranker-v2-m3",
            use_fp16=True,
            devices=["cuda:0"],
        )
        print("[reranker] 로딩 완료")
    return _reranker


def warm_up_reranker():
    """앱 구동 시 리랭커 워밍업 (첫 쿼리 타임아웃 방지)"""
    try:
        print("[reranker] 워밍업 시작...")
        reranker = _get_reranker()
        reranker.compute_score([["init", "warm up"]], normalize=True)
        print("[reranker] 워밍업 완료")
    except Exception as e:
        print(f"[reranker 워밍업 실패]: {e}")


def _rerank(query: str, results: list[dict]) -> list[dict]:
    """리랭킹 후 reranker_score 추가. 실패 시 hybrid_score로 fallback."""
    if not results:
        return results
    try:
        reranker = _get_reranker()
        pairs  = [[query, r.get("content", "")] for r in results]
        scores = reranker.compute_score(pairs, normalize=True)
        if isinstance(scores, float):
            scores = [scores]
        for r, s in zip(results, scores):
            r["reranker_score"] = float(s)
    except Exception as e:
        print(f"[reranker] 실패, hybrid_score로 fallback: {e}")
        for r in results:
            r["reranker_score"] = r.get("score", 0.0)
    return results


# ── 하이브리드 검색 (단일 컬렉션) ────────────────────────────
def _search_collection(
    query_text: str,
    collection_name: str,
    top_k: int = CANDIDATE_K,
    where: dict | None = None,
) -> list[dict]:
    """컬렉션 하나에서 하이브리드 검색 수행."""
    collection = _get_collection(collection_name)
    results    = []

    try:
        query_kwargs = {
            "query_texts": [query_text],
            "n_results":   top_k,
            "include":     ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        dense = collection.query(**query_kwargs)
    except Exception as e:
        print(f"[search] {collection_name} 검색 실패: {e}")
        return []

    documents = dense.get("documents", [[]])[0]
    ids       = dense.get("ids", [[]])[0]
    metadatas = dense.get("metadatas", [[]])[0]
    distances = dense.get("distances", [[]])[0]

    if not documents:
        return []

    # BM25 점수 계산
    index_data  = _load_bm25_index(collection_name)
    bm25        = _build_bm25(index_data["tokenized_docs"])
    bm25_scores = bm25.get_scores(query_text.split())
    bm25_map    = {
        index_data["doc_ids"][i]: bm25_scores[i]
        for i in range(len(index_data["doc_ids"]))
    }
    max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0

    for i in range(len(documents)):
        doc_id         = ids[i]
        distance       = distances[i] if distances else 1.0
        semantic_score = 1.0 - distance
        raw_bm25       = bm25_map.get(doc_id, 0.0)
        keyword_score  = min(raw_bm25 / max_bm25, 1.0)
        final_score    = (semantic_score * VECTOR_WEIGHT) + (keyword_score * BM25_WEIGHT)
        meta           = metadatas[i]

        results.append({
            "id":           doc_id,
            "content":      documents[i],
            "metadata":     meta,
            "score":        round(final_score, 4),
            "collection":   collection_name,
            # 법조문용
            "법령명":       meta.get("법령명", ""),
            "조문번호":     meta.get("조문번호", ""),
            "항번호":       meta.get("항번호", ""),
            "조문제목":     meta.get("조문제목", ""),
            # 판례용
            "판례번호":     meta.get("판례번호", ""),
            "법원명":       meta.get("법원명", ""),
            "선고일자":     meta.get("선고일자", ""),
            "섹션타입":     meta.get("섹션타입", ""),
            "status":       meta.get("status", "active"),
            "superseded_by": meta.get("superseded_by", ""),
            # 공통
            "doc_category": meta.get("doc_category", ""),
            "document_id":  meta.get("document_id", ""),
            "chunk_index":  meta.get("chunk_index", 0),
        })

    return results


# ── 판례 sibling 청크 묶기 ────────────────────────────────────
def _get_precedent_siblings(판례번호: str) -> list[dict]:
    """
    같은 판례번호의 핵심 섹션 청크 자동 추가.
    (판시사항 / 판결요지 / 참조조문 / 참조판례)
    overruled 판례는 경고 표시 포함.
    """
    if not 판례번호:
        return []

    collection = _get_collection(LEGAL_CORPUS)
    try:
        result = collection.get(
            where={
                "$and": [
                    {"판례번호": {"$eq": 판례번호}},
                    {"섹션타입": {"$in": CORE_SECTIONS}},
                ]
            },
            include=["documents", "metadatas"]
        )
    except Exception as e:
        print(f"[sibling] 판례 sibling 조회 실패: {e}")
        return []

    siblings = []
    for doc, meta in zip(result.get("documents", []), result.get("metadatas", [])):
        item = {
            "content":      doc,
            "metadata":     meta,
            "판례번호":     meta.get("판례번호", ""),
            "섹션타입":     meta.get("섹션타입", ""),
            "status":       meta.get("status", "active"),
            "superseded_by": meta.get("superseded_by", ""),
            "is_sibling":   True,
            "overruled_warning": meta.get("status") == "overruled",
        }
        siblings.append(item)

    return siblings


# ── intent별 where 조건 빌더 ─────────────────────────────────
def _build_legal_corpus_where(intent: str) -> dict | None:
    """intent에 따라 legal_corpus 검색 필터 생성."""
    if intent == "statute_search":
        return {"$and": [
            {"doc_category": {"$eq": "statute"}},
            {"법령구분명": {"$eq": "법률"}}
        ]}
    elif intent == "precedent_search":
        return {"doc_category": {"$eq": "precedent"}}
    else:
        # legal_search, contract_risk_check → 필터 없음 (전체)
        return None

def _build_user_docs_where(
    intent: str,
    uploaded_document_id: str | None,
    conversation_id: str | None,
) -> dict | None:
    """intent와 케이스에 따라 user_documents 검색 필터 생성."""
    # user_documents 검색이 필요한 intent만
    if intent not in ["contract_risk_check", "legal_search"]:
        return None

    # 케이스 A: 방금 올린 문서
    if uploaded_document_id:
        return {"document_id": {"$eq": uploaded_document_id}}

    # 케이스 B: 이 채팅방 전체 문서
    if conversation_id:
        return {"conversation_id": {"$eq": conversation_id}}

    return None


# ── 메인 검색 함수 ────────────────────────────────────────────
def search(
    query_text: str,
    intent: str,
    uploaded_document_id: str | None = None,
    conversation_id: str | None = None,
    top_k: int = FINAL_K,
) -> dict:
    """
    법률 AI용 하이브리드 RAG 검색.

    Args:
        query_text: 검색 쿼리
        intent: 의도 분류 결과
        uploaded_document_id: 방금 업로드된 문서 ID (케이스 A)
        conversation_id: 채팅방 ID (케이스 B)
        top_k: 최종 반환 청크 수

    Returns:
        {
            "results": [...],              # 최종 청크 리스트
            "needs_more_context": bool,    # 판례 전문 추가 필요 여부
            "overruled_warnings": [...],   # overruled 판례 경고 목록
        }
    """
    print(f"[search] intent={intent}, query={query_text[:50]}")

    all_candidates = []

    # ── 1. legal_corpus 검색 ──────────────────────────────────
    if intent != "general_answer":
        legal_where = _build_legal_corpus_where(intent)
        legal_results = _search_collection(
            query_text, LEGAL_CORPUS,
            top_k=CANDIDATE_K,
            where=legal_where
        )
        all_candidates.extend(legal_results)
        print(f"[search] legal_corpus: {len(legal_results)}개")

    # ── 2. user_documents 검색 ────────────────────────────────
    user_where = _build_user_docs_where(intent, uploaded_document_id, conversation_id)
    if user_where:
        user_results = _search_collection(
            query_text, USER_DOCUMENTS,
            top_k=CANDIDATE_K,
            where=user_where
        )
        all_candidates.extend(user_results)
        print(f"[search] user_documents: {len(user_results)}개")

    if not all_candidates:
        return {"results": [], "needs_more_context": False, "overruled_warnings": []}

    # ── 3. 점수 기준 정렬 후 리랭킹 ──────────────────────────
    all_candidates.sort(key=lambda x: x["score"], reverse=True)
    candidates_for_rerank = all_candidates[:CANDIDATE_K]
    reranked = _rerank(query_text, candidates_for_rerank)
    reranked.sort(key=lambda x: x["reranker_score"], reverse=True)
    top_results = reranked[:top_k]

    # ── 4. 판례 sibling 청크 묶기 ────────────────────────────
    seen_판례번호 = set()
    final_results = []

    for r in top_results:
        final_results.append(r)

        # 판례 청크인 경우 sibling 추가
        판례번호 = r.get("판례번호", "")
        if 판례번호 and 판례번호 not in seen_판례번호:
            seen_판례번호.add(판례번호)
            siblings = _get_precedent_siblings(판례번호)
            # 이미 있는 청크는 중복 추가 안 함
            existing_ids = {r2["id"] for r2 in final_results}
            for s in siblings:
                if s.get("id") not in existing_ids:
                    final_results.append(s)

    # ── 5. overruled 경고 수집 ────────────────────────────────
    overruled_warnings = []
    for r in final_results:
        if r.get("status") == "overruled":
            overruled_warnings.append({
                "판례번호":     r.get("판례번호", ""),
                "superseded_by": r.get("superseded_by", ""),
            })

    # ── 6. needs_more_context 판단 ───────────────────────────
    # 최상위 결과의 reranker_score가 낮으면 전문 추가 필요
    top_score = top_results[0].get("reranker_score", 0.0) if top_results else 0.0
    needs_more_context = top_score < CONFIDENCE_THRESHOLD

    print(f"[search] 최종: {len(final_results)}개, top_score={top_score:.3f}, needs_more_context={needs_more_context}")

    return {
        "results":           final_results,
        "needs_more_context": needs_more_context,
        "overruled_warnings": overruled_warnings,
    }


# ── 판례 전문 추가 검색 (needs_more_context=True 시) ─────────
def search_precedent_full_text(판례번호: str, query_text: str, top_k: int = 3) -> list[dict]:
    """
    판례 전문(이유) 청크 추가 검색.
    needs_more_context=True일 때 2차 검색으로 호출.
    """
    collection = _get_collection(LEGAL_CORPUS)
    try:
        result = collection.query(
            query_texts=[query_text],
            n_results=top_k,
            where={
                "$and": [
                    {"판례번호": {"$eq": 판례번호}},
                    {"섹션타입": {"$eq": "전문"}},
                ]
            },
            include=["documents", "metadatas", "distances"]
        )
    except Exception as e:
        print(f"[전문검색] 실패: {e}")
        return []

    docs  = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]

    return [
        {
            "content":  doc,
            "metadata": meta,
            "판례번호": meta.get("판례번호", ""),
            "섹션타입": "전문",
            "is_full_text": True,
        }
        for doc, meta in zip(docs, metas)
    ]


# ── 테스트 ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== 법률 RAG 검색 테스트 ===\n")

    test_cases = [
        # ── 정확 매칭형 (조문번호 직접 지정 — 키워드 매칭 강해야 함)
        ("주택임대차보호법 제3조 대항력",              "statute_search"),
        ("민법 제390조 채무불이행",                    "statute_search"),
        ("부동산등기법 등기신청 의무",                  "statute_search"),

        # ── 개념 검색형 (조문번호 없이 상황 설명 — 의미 검색 강해야 함)
        ("전세보증금 못 돌려받으면 어떻게 해야 하나요",  "statute_search"),
        ("공인중개사가 중개 잘못했을 때 책임",           "statute_search"),
        ("계약 어기면 손해배상 얼마나 물어야 하나",       "statute_search"),

        # ── 소분류 교차 확인형 (비슷한 법령끼리 헷갈리는지)
        ("상가 임대차 계약 갱신 요구권",                "statute_search"),  # 상가임대차 vs 주택임대차 구분되는지
        ("보증인 책임 범위",                           "statute_search"),  # 민법 vs 보증인보호특별법 구분되는지
]

    for query, intent in test_cases:
        print(f"[{intent}] {query}")
        result = search(query, intent)
        print(f"  → {len(result['results'])}개 반환")
        print(f"  → needs_more_context: {result['needs_more_context']}")
        if result["overruled_warnings"]:
            print(f"  → ⚠️ overruled 판례: {result['overruled_warnings']}")
        if result["results"]:
            print("  상위 결과:")
            for r in result["results"][:3]:
                print(f"    - {r.get('법령명')} {r.get('조문번호')}조 score={r.get('reranker_score', 0):.3f}")
                print(f"      {r.get('content', '')[:80]}")
        print()