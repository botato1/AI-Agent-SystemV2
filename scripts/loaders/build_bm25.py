# scripts/loaders/build_bm25.py
import chromadb
import pickle
import os
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

ef = SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-m3")
c = chromadb.PersistentClient(path="./storage/chroma")
col = c.get_collection("legal_corpus", embedding_function=ef)

result = col.get(include=["documents"])
ids = result["ids"]
documents = result["documents"]

print(f"총 {len(ids)}개 청크로 BM25 인덱스 빌드 중...")

index_data = {
    "doc_ids": ids,
    "tokenized_docs": [doc.split() for doc in documents]
}

os.makedirs("./storage/bm25", exist_ok=True)
with open("./storage/bm25/legal_corpus.pkl", "wb") as f:
    pickle.dump(index_data, f)

print("완료!")