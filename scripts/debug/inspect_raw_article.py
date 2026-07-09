# scripts/debug/inspect_raw_article.py
#
# law.go.kr API 원본 응답에서 '항' 관련 필드가 실제로 어떤 키/구조로
# 내려오는지 확인하기 위한 스크립트.
#
# chunk_articles()의 항 분리 로직이 조문내용 안의 ①②③ 텍스트만 보고 있는데,
# 항이 있는 조문(예: 민법 429조)에서 본문이 사라지는 버그의 원인을
# raw JSON을 직접 찍어서 확인한다.
#
# 실행:
#   python scripts/debug/inspect_raw_article.py

import json
import requests

OC          = "ai-agent-system-legal"
CONTENT_URL = "http://www.law.go.kr/DRF/lawService.do"
TIMEOUT     = 30

# 진단 대상: 민법(MST=284415) 429조 — 항 있는데 본문 사라진 케이스
MST = "284415"
TARGET_조문번호 = "429"


def fetch_raw(mst: str) -> dict:
    params = {"OC": OC, "target": "law", "MST": mst, "type": "JSON"}
    res = requests.get(CONTENT_URL, params=params, timeout=TIMEOUT)
    return res.json()


def find_article(data: dict, 조문번호: str) -> dict | None:
    articles = data.get("법령", {}).get("조문", {}).get("조문단위", [])
    if isinstance(articles, dict):
        articles = [articles]
    for a in articles:
        if str(a.get("조문번호", "")) == 조문번호:
            return a
    return None


def main():
    print(f"MST={MST} 조회 중...")
    data = fetch_raw(MST)

    article = find_article(data, TARGET_조문번호)
    if article is None:
        print(f"조문번호={TARGET_조문번호} 못 찾음. 첫 조문 구조라도 출력:")
        articles = data.get("법령", {}).get("조문", {}).get("조문단위", [])
        if isinstance(articles, dict):
            articles = [articles]
        article = articles[0] if articles else {}

    print("=" * 70)
    print(f"조문번호={TARGET_조문번호} 원본 구조 (전체 키 + 값)")
    print("=" * 70)
    print(json.dumps(article, ensure_ascii=False, indent=2))

    print()
    print("=" * 70)
    print("최상위 키 목록:", list(article.keys()))
    print("=" * 70)


if __name__ == "__main__":
    main()