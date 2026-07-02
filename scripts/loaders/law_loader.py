"""
scripts/loaders/law_loader.py
law.go.kr API → 청킹 → ChromaDB 적재 (final)

실행:
    python scripts/loaders/law_loader.py

동작:
    1. law_category_list.json에서 법령 목록 자동 로드
    2. 법률 + 대통령령만 필터링
    3. 미래 시행일자 법령 스킵 (오늘 날짜 기준)
    4. 중복/개정 체크 후 적재
"""

import re
import json
import time
import requests
import chromadb
from datetime import datetime
from pathlib import Path
from chromadb.utils import embedding_functions

# ============================================================
# 설정
# ============================================================
OC          = "ai-agent-system-legal"
SEARCH_URL  = "http://www.law.go.kr/DRF/lawSearch.do"
CONTENT_URL = "http://www.law.go.kr/DRF/lawService.do"
CHROMA_PATH = "./storage/chroma"
COLLECTION  = "legal_corpus"
BATCH_SIZE  = 50
DELAY       = 1.0
TIMEOUT     = 30

# 법령분류 코드 → (법령대분류, 법령분류) 매핑
CATEGORY_MAP = {
    "08": ("사법", "민사법"),
    "09": ("공법", "형사법"),
    "07": ("사법", "법무"),
    "34": ("사법", "민사법"),
    "33": ("사법", "민사법"),
    "35": ("사법", "민사법"),
}

# 적재할 법령 종류
ALLOWED_LAW_TYPES = {"법률", "대통령령"}

# 법령 목록 JSON 경로
CATEGORY_LIST_PATH = "scripts/crawlers/law_category_list.json"


# ============================================================
# 법령 목록 로드
# ============================================================
def load_law_targets() -> list[dict]:
    path = Path(CATEGORY_LIST_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"{CATEGORY_LIST_PATH} 없음. "
            "먼저 law_category_crawler.py 실행해서 목록 수집하세요."
        )

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    targets = []
    for 분류명, laws in data.items():
        for law in laws:
            if law.get("법령구분명") not in ALLOWED_LAW_TYPES:
                continue

            code = law.get("법령분류코드", "")
            대분류, 분류 = CATEGORY_MAP.get(code, ("기타", 분류명))

            targets.append({
                "법령명":     law["법령명"],
                "MST":        law["MST"],
                "시행일자":   law["시행일자"],
                "법령구분명": law["법령구분명"],
                "법령대분류": 대분류,
                "법령분류":   분류,
                "법령소분류": law.get("법령분류명", 분류명),
                "소관부처명": law.get("소관부처명", ""),
            })

    return targets


# ============================================================
# API 호출
# ============================================================
def fetch_law_content(mst: str) -> list[dict]:
    params = {"OC": OC, "target": "law", "MST": mst, "type": "JSON"}
    res = requests.get(CONTENT_URL, params=params, timeout=TIMEOUT)
    data = res.json()
    articles = data.get("법령", {}).get("조문", {}).get("조문단위", [])
    return [articles] if isinstance(articles, dict) else articles


# ============================================================
# 청킹 — 조/항 단위 규칙 기반
# ============================================================
def chunk_articles(articles: list[dict], law_meta: dict) -> list[dict]:
    chunks = []
    chunk_index = 0

    for article in articles:
        조문번호 = article.get("조문번호", "")
        조문내용 = article.get("조문내용", "")
        if isinstance(조문내용, list):
            조문내용 = " ".join(str(x) for x in 조문내용)
        조문내용 = str(조문내용).strip()
        조문제목 = article.get("조문제목", "")
        시행일자 = article.get("조문시행일자", law_meta["시행일자"])

        if not 조문내용:
            continue

        항_파트 = re.split(r'(?=\s*[①②③④⑤⑥⑦⑧⑨⑩])', 조문내용)
        항_파트 = [p.strip() for p in 항_파트 if p.strip()]

        base_meta = {
            # 사용자 노출용
            "법령명":       law_meta["법령명"],
            "조문번호":     조문번호,
            "조문제목":     조문제목,
            # 내부 필터링용
            "doc_category": "statute",
            "법령대분류":   law_meta["법령대분류"],
            "법령분류":     law_meta["법령분류"],
            "법령소분류":   law_meta["법령소분류"],
            "법령구분명":   law_meta["법령구분명"],
            "소관부처명":   law_meta["소관부처명"],
            "법령ID":       law_meta.get("법령ID", ""),
            "MST":          law_meta["MST"],
            "시행일자":     시행일자,
        }

        if len(항_파트) > 1:
            for 항_idx, 항_내용 in enumerate(항_파트):
                meta = {**base_meta, "항번호": str(항_idx + 1), "chunk_index": chunk_index}
                chunks.append({"content": 항_내용, "metadata": meta})
                chunk_index += 1
        else:
            meta = {**base_meta, "항번호": "", "chunk_index": chunk_index}
            chunks.append({"content": 조문내용, "metadata": meta})
            chunk_index += 1

    return chunks


# ============================================================
# ChromaDB
# ============================================================
def get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="BAAI/bge-m3"
    )
    return client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )


def get_existing_시행일자(collection, mst: str) -> str | None:
    try:
        result = collection.get(where={"MST": mst}, limit=1)
        if result["metadatas"]:
            return result["metadatas"][0].get("시행일자")
    except Exception:
        pass
    return None


def delete_law_chunks(collection, mst: str):
    result = collection.get(where={"MST": mst})
    if result["ids"]:
        collection.delete(ids=result["ids"])
        print(f"  기존 청크 {len(result['ids'])}개 삭제")


def upsert_chunks(collection, chunks: list[dict], law_name: str):
    ids = [
        f"{c['metadata']['MST']}_{c['metadata']['조문번호']}_{c['metadata']['항번호']}_{c['metadata']['chunk_index']}"
        for c in chunks
    ]
    documents = [c["content"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    for i in range(0, len(chunks), BATCH_SIZE):
        collection.upsert(
            ids=ids[i:i+BATCH_SIZE],
            documents=documents[i:i+BATCH_SIZE],
            metadatas=metadatas[i:i+BATCH_SIZE],
        )
        print(f"  적재 중... {min(i+BATCH_SIZE, len(chunks))}/{len(chunks)}")

    print(f"  ✓ {law_name} → {len(chunks)}개 청크 완료")


# ============================================================
# 메인 파이프라인
# ============================================================
def run():
    TODAY = datetime.now().strftime("%Y%m%d")

    print("=" * 60)
    print("law.go.kr 법령 수집 → ChromaDB 적재")
    print(f"오늘 기준일: {TODAY}")
    print("=" * 60)

    try:
        targets = load_law_targets()
    except FileNotFoundError as e:
        print(f"오류: {e}")
        return

    print(f"수집 대상: {len(targets)}개 법령 (법률 + 대통령령)")

    collection = get_collection()
    success = 0
    skip = 0
    fail = 0

    for law in targets:
        mst      = law["MST"]
        법령명   = law["법령명"]
        시행일자 = law["시행일자"]

        print(f"\n  [{law['법령분류']}] {법령명} 처리 중...")

        # 0. 미래 시행일자 스킵
        if 시행일자 > TODAY:
            print(f"  미래 시행일자 ({시행일자}) — 스킵")
            skip += 1
            continue

        # 1. 중복/개정 체크
        existing = get_existing_시행일자(collection, mst)
        if existing:
            if 시행일자 <= existing:
                print(f"  최신 버전 존재 (시행일: {existing}) — 스킵")
                skip += 1
                continue
            print(f"  개정 감지 ({existing} → {시행일자}) — 재적재")
            delete_law_chunks(collection, mst)
        else:
            print(f"  신규 적재 (시행일: {시행일자})")

        # 2. 본문 수집
        try:
            time.sleep(DELAY)
            articles = fetch_law_content(mst)
        except Exception as e:
            print(f"  본문 수집 실패: {e} — 스킵")
            fail += 1
            continue

        if not articles:
            print(f"  조문 없음 — 스킵")
            fail += 1
            continue

        print(f"  조문 {len(articles)}개 수집")

        # 3. 청킹
        chunks = chunk_articles(articles, law)
        print(f"  청킹 → {len(chunks)}개 청크")

        # 4. 적재
        upsert_chunks(collection, chunks, 법령명)
        success += 1
        time.sleep(DELAY)

    print("\n" + "=" * 60)
    print(f"완료 — 성공: {success} / 스킵: {skip} / 실패: {fail}")
    print(f"ChromaDB 총 청크 수: {collection.count()}")
    print("=" * 60)


if __name__ == "__main__":
    run()