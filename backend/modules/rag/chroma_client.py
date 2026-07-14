# backend/modules/rag/chroma_client.py
import os
import sys
import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ── 네이티브 라이브러리 import 순서 고정 ──────────────────────
# [수정 사항 - 2026.06.18]
# 증상: FlagEmbedding(리랭커)을 import하는 시점에 Windows에서
#       access violation(0xC0000005)으로 파이썬 프로세스가 죽는 문제가 있었음.
# 원인 조사: faulthandler로 스택트레이스를 떠보니, 죽는 지점은 항상
#       pyarrow였음 (pandas.compat.pyarrow → pyarrow, 또는
#       datasets.packaged_modules → pyarrow.dataset → pyarrow 경로).
#       다만 torch/pandas/sklearn/transformers/datasets를 미리
#       이 순서로 import해둔 다음 sentence_transformers나
#       FlagEmbedding을 import하면 죽지 않는 것이 실측으로 확인됨.
#       즉 pyarrow 자체가 손상된 게 아니라, 어떤 네이티브 라이브러리가
#       먼저 초기화되느냐에 따라 충돌 여부가 갈리는 "초기화 순서" 문제.
# 조치: 이 파일에서 FlagEmbedding을 쓰기 전에, 검증된 순서로
#       미리 import해서 충돌을 회피함. 이 블록을 지우면 reranker가
#       다시 죽을 수 있으니 임의로 제거하지 말 것.
import torch        # noqa: F401
import pandas        # noqa: F401
import sklearn        # noqa: F401
import transformers   # noqa: F401
import datasets       # noqa: F401

BASE_DIR = Path(__file__).resolve().parents[3]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

CHROMA_DIR = os.path.join(BASE_DIR, "storage", "chroma")
BM25_DIR = os.path.join(BASE_DIR, "storage", "bm25")
os.makedirs(BM25_DIR, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

# ── 컬렉션 이름 상수 ──────────────────────────────────────────
MEETING_COLLECTION  = "meeting_collection"
DOCUMENT_COLLECTION = "document_collection"
KNOWLEDGE_COLLECTION = "knowledge_collection"

CONTEXT_TO_COLLECTION = {
    "voice":    MEETING_COLLECTION,
    "meeting":  MEETING_COLLECTION,
    "document": DOCUMENT_COLLECTION,
}


# ── 컬렉션 ────────────────────────────────────────────────────
def get_or_create_collection(collection_name: str):
    ollama_ef = OllamaEmbeddingFunction(
        url="http://localhost:11434/api/embeddings",
        model_name="bge-m3"
    )
    return chroma_client.get_or_create_collection(
        name=collection_name,
        embedding_function=ollama_ef,
        metadata={"hnsw:space": "cosine"}
    )


# ── BM25 인덱스 관리 ──────────────────────────────────────────
#
# [수정 사항 - 2026.07.14] Re:Call v2 마이그레이션: workspace_id 단위 분리
# 기존에는 collection_name 하나로만 인덱스 파일을 나눠서, 모든 워크스페이스의
# 문서가 같은 BM25 인덱스에 쌓였음. 이러면 (1) 스코어 정규화(max_bm25)가
# 다른 워크스페이스 데이터에 의해 왜곡되고 (2) 워크스페이스가 늘어날수록
# 인덱스 파일 하나가 무한정 커짐. collection_name + workspace_id 조합으로
# 인덱스 파일을 분리해서 두 문제 모두 해결.
def _bm25_path(collection_name: str, workspace_id: str) -> str:
    return os.path.join(BM25_DIR, f"{collection_name}__{workspace_id}.pkl")


def _load_bm25_index(collection_name: str, workspace_id: str) -> dict:
    path = _bm25_path(collection_name, workspace_id)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return {"doc_ids": [], "tokenized_docs": []}


def _save_bm25_index(collection_name: str, workspace_id: str, index_data: dict):
    path = _bm25_path(collection_name, workspace_id)
    with open(path, "wb") as f:
        pickle.dump(index_data, f)


def _build_bm25(tokenized_docs: list) -> BM25Okapi:
    if not tokenized_docs:
        return BM25Okapi([[""]])
    return BM25Okapi(tokenized_docs)


def _update_bm25_index(collection_name: str, workspace_id: str, doc_id: str, document: str):
    index_data = _load_bm25_index(collection_name, workspace_id)
    index_data["doc_ids"].append(doc_id)
    index_data["tokenized_docs"].append(document.split())
    _save_bm25_index(collection_name, workspace_id, index_data)


def _remove_from_bm25_index(collection_name: str, workspace_id: str, doc_id: str):
    index_data = _load_bm25_index(collection_name, workspace_id)
    if doc_id in index_data["doc_ids"]:
        idx = index_data["doc_ids"].index(doc_id)
        index_data["doc_ids"].pop(idx)
        index_data["tokenized_docs"].pop(idx)
        _save_bm25_index(collection_name, workspace_id, index_data)


# ── 문서 저장 ─────────────────────────────────────────────────
#
# [수정 사항 - 2026.07.14] Re:Call v2 마이그레이션: 테넌트 격리 추가
# 문제: 기존에는 metadata에 workspace_id가 없어서, 여러 워크스페이스가 같은
#       collection(meeting/document/knowledge)을 공유할 때 검색 결과가
#       워크스페이스 경계 없이 섞일 수 있었음. BM25 인덱스도 collection_name
#       단위로만 분리돼서 같은 문제가 있었음.
# 조치: doc["workspace_id"]를 필수값으로 받고 metadata에 포함, BM25 인덱스도
#       (collection_name, workspace_id) 조합으로 분리 저장.
#       category_id는 선택값(옵션)이지만 넘기면 함께 저장 — MVP는 워크스페이스당
#       카테고리 1개뿐이라 지금은 필터링에 큰 영향 없지만, 카테고리 여러 개로
#       늘어날 때 마이그레이션 없이 바로 필터링 가능하게 미리 반영해둠.
def insert_document(doc: dict):
    workspace_id = doc.get("workspace_id")
    if not workspace_id:
        raise ValueError(
            "insert_document: workspace_id는 필수입니다. "
            "테넌트 격리 없이 저장하면 다른 워크스페이스 검색 결과와 섞일 수 있습니다."
        )

    upload_context = doc.get("upload_context", "document")
    collection_name = CONTEXT_TO_COLLECTION.get(upload_context, KNOWLEDGE_COLLECTION)
    collection = get_or_create_collection(collection_name)

    tags = doc.get("tags", [])
    if isinstance(tags, list):
        tags = ",".join(tags)

    metadata = {
        "workspace_id":     workspace_id,
        "category_id":      doc.get("category_id", ""),
        "title":            doc.get("title", ""),
        "type":             doc.get("type", "document"),
        "source":           doc.get("source", ""),
        "language":         doc.get("language", "ko"),
        "created_at":       doc.get("created_at", ""),
        "status":           doc.get("status", "processed"),
        "notion_url":       doc.get("notion_url") or "",
        "chroma_id":        doc.get("id", ""),
        "error":            doc.get("error") or "",
        "user_edited":      doc.get("user_edited", False),
        "tags":             tags,
        "importance_score": doc.get("importance_score", 50),
        "document_id":      doc.get("document_id", ""),
        "filename":         doc.get("filename", ""),
        "upload_context":   upload_context,
        "chunk_index":      doc.get("chunk_index", 0),
        "room_id":          doc.get("room_id", ""),
        "tech_score":       doc.get("tech_score", 0),
    }

    collection.add(
        ids=[doc["id"]],
        documents=[doc["content"]],
        metadatas=[metadata]
    )
    _update_bm25_index(collection_name, workspace_id, doc["id"], doc["content"])
    print(f"[BGE-M3] 저장 완료 → {collection_name} (workspace={workspace_id}): {doc.get('title', doc['id'])}")


# ── Reranker ─────────────────────────────────────────────────
_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None:
        from FlagEmbedding import FlagReranker
        # [수정 - 2026.06.18] CPU/fp32 -> GPU/fp16로 재전환 시도.
        # 기존에는 GPU+fp16 조합에서 프로세스가 에러 없이 죽는 문제가 있어
        # CPU/fp32로 고정했었음. 그 문제가 사실은 이 파일 상단에 추가된
        # import 순서 고정 코드로 해결한 access violation과 같은 종류의
        # 문제였을 가능성이 있어 재시도함. CANDIDATE_K=60 기준 쿼리당
        # 3분 이상 걸리던 속도 문제 해결 목적.
        # 만약 다시 죽거나 OOM이 나면 use_fp16=False, devices=["cpu"]로
        # 되돌릴 것 (단, 그러면 속도 문제도 같이 되돌아옴 — CANDIDATE_K를
        # 줄이는 방향으로 대신 접근).
        print("[reranker] BAAI/bge-reranker-v2-m3 로딩 중 (GPU, fp16)...")
        _reranker = FlagReranker(
            "BAAI/bge-reranker-v2-m3",
            use_fp16=True,
            devices=["cuda:0"],
        )
        print("[reranker] 로딩 완료")
    return _reranker

# [추가] 서비스 초기화 시점에 호출할 Warm-up 함수
def warm_up_reranker():
    """앱 구동 시 리랭커를 메모리에 미리 올려 첫 쿼리 타임아웃을 방지합니다."""
    try:
        print("[reranker] 초기화 워밍업 시작...")
        reranker = _get_reranker()
        # 가벼운 더미 데이터로 강제 추론 구동
        reranker.compute_score([["init", "warm up"]], normalize=True)
        print("[reranker] 초기화 워밍업 완료.")
    except Exception as e:
        print(f"[reranker 워밍업 실패]: {e}")

def rerank_results(query_text: str, results: list[dict]) -> list[dict]:
    """
    results 각각의 content와 query를 cross-encoder로 재평가.
    각 결과에 reranker_score 필드를 추가하고 반환 (정렬은 하지 않음).
    FlagEmbedding 미설치/로딩실패 시 reranker_score = hybrid_score로 fallback.
    """
    if not results:
        return results

    try:
        reranker = _get_reranker()
        pairs = [[query_text, r.get("content", "")] for r in results]
        scores = reranker.compute_score(pairs, normalize=True)

        if isinstance(scores, float):
            scores = [scores]

        for r, s in zip(results, scores):
            r["reranker_score"] = float(s)

    except Exception as e:
        print(f"[rerank_results] reranker 실패, hybrid_score로 fallback: {e}")
        for r in results:
            r["reranker_score"] = r.get("score", 0.0)

    return results


# ── 하이브리드 검색 ───────────────────────────────────────────
#
# [수정 사항 - 2026.07.14] Re:Call v2 마이그레이션: workspace_id 필수화
# workspace_id를 필수 파라미터로 받아서 항상 where filter에 자동 병합함.
# 호출부에서 filter={"workspace_id": ...}를 깜빡 빼먹어도 다른 워크스페이스
# 데이터가 섞여 들어오지 않도록 함수 자체에서 강제. category_id는 선택값 —
# MVP는 워크스페이스당 카테고리 1개뿐이라 지금은 넘기지 않아도 결과가
# 동일하지만, 카테고리 여러 개가 되는 시점부터는 넘겨야 정확히 스코프됨.
def search_hybrid(
    query_text: str,
    workspace_id: str,
    category_id: str | None = None,
    top_k: int = 60,
    filter: dict | None = None,
    collection_name: str | None = None
):
    target_collections = [collection_name] if collection_name else [
        MEETING_COLLECTION, DOCUMENT_COLLECTION, KNOWLEDGE_COLLECTION
    ]

    # workspace_id(+category_id)를 항상 where filter에 강제 병합
    merged_filter = dict(filter) if filter else {}
    merged_filter["workspace_id"] = workspace_id
    if category_id:
        merged_filter["category_id"] = category_id

    all_results = []

    print("[search_hybrid] query_text:", query_text)
    print("[search_hybrid] filter:", merged_filter)
    print("[search_hybrid] target_collections:", target_collections)

    for col_name in target_collections:
        collection = get_or_create_collection(col_name)

        try:
            query_kwargs = {
                "query_texts": [query_text],
                "n_results": top_k,
                "include": ["documents", "metadatas", "distances"],
                "where": merged_filter,
            }

            dense_results = collection.query(**query_kwargs)

        except Exception as e:
            print(f"[search_hybrid 에러] collection: {col_name}, error: {e}")
            continue

        if not dense_results:
            continue

        documents = dense_results.get("documents", [[]])
        ids       = dense_results.get("ids", [[]])
        metadatas = dense_results.get("metadatas", [[]])
        distances = dense_results.get("distances", [[]])

        if not documents or not documents[0]:
            continue

        print(f"[search_hybrid] collection: {col_name}, dense count: {len(documents[0])}")

        # BM25도 워크스페이스 단위 인덱스만 사용 → 다른 워크스페이스 문서가
        # 점수 정규화(max_bm25)에 영향을 주지 않음
        index_data = _load_bm25_index(col_name, workspace_id)
        bm25       = _build_bm25(index_data["tokenized_docs"])
        bm25_scores = bm25.get_scores(query_text.split())

        bm25_score_map = {
            index_data["doc_ids"][i]: bm25_scores[i]
            for i in range(len(index_data["doc_ids"]))
        }
        max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0

        for i in range(len(documents[0])):
            doc_id   = ids[0][i]
            document = documents[0][i]
            metadata = metadatas[0][i]
            distance = distances[0][i] if distances and distances[0] else 1.0

            semantic_score = 1.0 - distance
            raw_bm25       = bm25_score_map.get(doc_id, 0.0)
            keyword_score  = min(raw_bm25 / max_bm25, 1.0)
            final_score    = (semantic_score * 0.7) + (keyword_score * 0.3)

            all_results.append({
                "id":          doc_id,
                "content":     document,
                "document":    document,
                "metadata":    metadata,
                "score":       round(final_score, 4),
                "collection":  col_name,
                "title":       metadata.get("title", ""),
                "source":      metadata.get("source", ""),
                "filename":    metadata.get("filename", ""),
                "document_id": metadata.get("document_id", ""),
                "room_id":     metadata.get("room_id", ""),
                "chunk_index": metadata.get("chunk_index", 0),
            })

    all_results.sort(key=lambda x: x["score"], reverse=True)
    print("[search_hybrid] final count:", len(all_results[:top_k]))
    return all_results[:top_k]


# ── ChromaDB 직접 확인용 ──────────────────────────────────────
#
# [수정 사항 - 2026.07.14] workspace_id 필터 추가 (테넌트 격리)
def get_documents_by_document_id(document_id: str, workspace_id: str) -> dict:
    total_ids, total_metadatas, total_documents = [], [], []

    for collection_name in [MEETING_COLLECTION, DOCUMENT_COLLECTION, KNOWLEDGE_COLLECTION]:
        collection = get_or_create_collection(collection_name)
        try:
            result = collection.get(
                where={"$and": [{"document_id": document_id}, {"workspace_id": workspace_id}]},
                include=["metadatas", "documents"]
            )
            total_ids.extend(result.get("ids", []))
            total_metadatas.extend(result.get("metadatas", []))
            total_documents.extend(result.get("documents", []))
        except Exception as e:
            print(f"[Chroma get 에러] collection: {collection_name}, error: {e}")

    return {
        "ids":       total_ids,
        "metadatas": total_metadatas,
        "documents": total_documents,
        "count":     len(total_ids),
    }


# ── 문서 삭제 ─────────────────────────────────────────────────
#
# [수정 사항 - 2026.07.14] workspace_id 필터/BM25 인덱스 분리 반영
def delete_document(doc_id: str, workspace_id: str, collection_name: str | None = None):
    targets = [collection_name] if collection_name else [
        MEETING_COLLECTION, DOCUMENT_COLLECTION, KNOWLEDGE_COLLECTION
    ]
    for col_name in targets:
        try:
            collection = get_or_create_collection(col_name)
            result = collection.get(
                where={"$and": [{"document_id": doc_id}, {"workspace_id": workspace_id}]},
                include=[],
            )
            chunk_ids = result.get("ids", [])
            if chunk_ids:
                collection.delete(ids=chunk_ids)
                for cid in chunk_ids:
                    _remove_from_bm25_index(col_name, workspace_id, cid)
                print(f"[삭제 완료] {col_name}: document_id={doc_id}, 청크 {len(chunk_ids)}개 삭제")
            else:
                print(f"[삭제 스킵] {col_name}: document_id={doc_id} 해당 청크 없음")
        except Exception as e:
            print(f"[삭제 에러] {col_name}: document_id={doc_id}, error: {e}")

if __name__ == "__main__":
    print("ChromaDB 연결 확인 중...")
    for name in [MEETING_COLLECTION, DOCUMENT_COLLECTION, KNOWLEDGE_COLLECTION]:
        col = get_or_create_collection(name)
        print(f"{name} 준비 완료: {col.name}")