# scripts/debug/inspect_legal_corpus.py
#
# ChromaDB legal_corpus 적재 상태 진단 스크립트
#
# 확인 항목:
#   1. 법령별 적재 청크 수 (LAW_TARGETS 대비 빠진 법령 있는지)
#   2. 특정 법령명+조문번호 청크 직접 조회 (content 있는지, 몇 개인지)
#   3. content가 비정상적으로 짧은(제목만 있는) 청크 탐지 — 부모/자식 중복 의심
#
# 실행:
#   python scripts/debug/inspect_legal_corpus.py

import os
import sys
from pathlib import Path
from collections import defaultdict

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

# import 순서 고정 (Windows access violation 방지) — legal_retriever.py와 동일 순서 유지
import torch        # noqa: F401
import pandas       # noqa: F401
import sklearn      # noqa: F401
import transformers # noqa: F401
import datasets     # noqa: F401

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

CHROMA_DIR = "./storage/chroma"
LEGAL_CORPUS = "legal_corpus"

# 본문이 있어야 정상인데 이 글자수 미만이면 "제목만 있는 청크"로 의심
SHORT_CONTENT_THRESHOLD = 15

# 확인하고 싶은 법령 목록 (LAW_TARGETS 기준 — 필요하면 수정)
TARGET_LAWS = [
    "주택임대차보호법",
    "상가건물 임대차보호법",
    "부동산등기법",
    "공인중개사법",
    "부동산 실권리자명의 등기에 관한 법률",
    "민법",
    "보증인 보호를 위한 특별법",
    "민사소송법",
    "민사집행법",
    "소송촉진 등에 관한 특례법",
]

# 실제로 못 찾겼던(또는 이상했던) 특정 조문 — 직접 지정 조회
SPOT_CHECKS = [
    ("민법", "390"),
    ("민법", "429"),
    ("주택임대차보호법", "3"),
    ("신탁법", "125"),
    ("공인중개사법", None),          # 조문번호 지정 안 하면 법령 전체
    ("보증인 보호를 위한 특별법", None),
]


def get_collection():
    ef = SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-m3")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_collection(name=LEGAL_CORPUS, embedding_function=ef)


def check_coverage(collection):
    """법령별 적재 청크 수 집계 — 아예 빠진 법령 탐지"""
    print("=" * 70)
    print("[1] 법령별 적재 청크 수 (statute만)")
    print("=" * 70)

    result = collection.get(
        where={"doc_category": {"$eq": "statute"}},
        include=["metadatas"],
    )
    metas = result.get("metadatas", [])

    counts = defaultdict(int)
    for m in metas:
        counts[m.get("법령명", "(없음)")] += 1

    for law in TARGET_LAWS:
        n = counts.get(law, 0)
        flag = "  ⚠️ 적재 안 됨!" if n == 0 else ""
        print(f"  {law:30s} : {n:4d}개{flag}")

    unexpected = set(counts.keys()) - set(TARGET_LAWS)
    if unexpected:
        print(f"\n  (TARGET_LAWS 목록에 없는데 적재된 법령 {len(unexpected)}개 — 정상일 수 있음)")

    print()


def spot_check(collection, 법령명: str, 조문번호: str | None):
    """특정 법령/조문 직접 조회 — content 유무, 개수, 중복 확인"""
    where = {"법령명": {"$eq": 법령명}}
    if 조문번호:
        where = {"$and": [where, {"조문번호": {"$eq": 조문번호}}]}

    result = collection.get(where=where, include=["documents", "metadatas"])
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])
    ids = result.get("ids", [])

    label = f"{법령명} {조문번호}조" if 조문번호 else f"{법령명} (전체)"
    print(f"── {label} : {len(docs)}개 청크 ──")

    if not docs:
        print("  ⚠️ 결과 없음 — 적재 자체가 안 됐거나 법령명 표기가 다를 수 있음")
        print()
        return

    for doc_id, doc, meta in zip(ids, docs, metas):
        content_len = len(doc or "")
        short_flag = "  ⚠️ 본문 없음/제목만 의심" if content_len < SHORT_CONTENT_THRESHOLD else ""
        preview = (doc or "")[:60].replace("\n", " ")
        print(f"  id={doc_id}")
        print(f"    조문번호={meta.get('조문번호')} 항번호={meta.get('항번호')} "
              f"chunk_index={meta.get('chunk_index')} len={content_len}{short_flag}")
        print(f"    content: {preview}")
    print()


def main():
    collection = get_collection()
    print(f"legal_corpus 총 청크 수: {collection.count()}\n")

    check_coverage(collection)

    print("=" * 70)
    print("[2] 개별 조문 직접 조회 (content 유무 / 중복 확인)")
    print("=" * 70)
    for 법령명, 조문번호 in SPOT_CHECKS:
        spot_check(collection, 법령명, 조문번호)


if __name__ == "__main__":
    main()