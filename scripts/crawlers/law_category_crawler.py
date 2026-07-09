"""
scripts/crawlers/law_category_crawler.py
law.go.kr 법령분류별 전체 목록 크롤링 (파싱 실패 로깅 추가본)

실행:
    python scripts/crawlers/law_category_crawler.py

[수정 사항]
    기존 코드는 개별 <li> 항목 파싱 중 예외가 나면
        except Exception:
            continue
    로 조용히 건너뛰어서, 특정 항목(예: 공인중개사법)이 왜 빠졌는지
    전혀 알 수 없었음.

    이번 수정본은:
      1. 실제 li 항목 수 vs 최종 파싱 성공 수를 비교해서 불일치하면 경고 출력
      2. 파싱 실패한 항목은 원인(어느 단계에서 실패했는지)과 함께
         raw HTML을 skipped_items 리스트에 모아서 별도 JSON으로 저장
      3. 법령명에 특정 검색 대상(예: "공인중개사법")이 포함된 li는
         파싱 성공 여부와 무관하게 raw onclick/HTML을 항상 로그로 남김
         (원인 특정을 위한 임시 디버깅 장치 — 원인 파악 후 제거 가능)
"""

import re
import json
import asyncio
from playwright.async_api import async_playwright

SEARCH_URL = "https://law.go.kr/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query="

# 수집할 법령분류 코드 (콤보박스 value값)
LAW_CLASS_CODES = {
    "08": "민사법",
    "09": "형사법",
    "07": "법무",
    "34": "주택·건축·도로",
    "33": "국토개발·도시",
    "35": "수자원·토지·건설업",
}

# 현재 수집할 분류
ACTIVE_CLASSES = ["08"]

# 파싱 성공 여부와 무관하게 항상 raw HTML/onclick을 찍어서 확인하고 싶은 키워드
WATCH_KEYWORDS = ["공인중개사법"]


async def fetch_law_list(browser, page, class_code: str, class_name: str) -> tuple[list[dict], list[dict]]:
    print(f"\n[{class_name}({class_code})] 목록 수집 중...")

    # 1. 페이지 접속
    await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(2000)

    # 2. POST로 전체 목록 가져오기
    response = await page.evaluate("""
        async (classCode) => {
            const params = new URLSearchParams();
            params.append('q', '*');
            params.append('outmax', '9999');
            params.append('p18', '0');
            params.append('p19', '1,3');
            params.append('pg', '1');
            params.append('fsort', '10,41,21,31');
            params.append('lsType', 'null');
            params.append('section', 'lawNm');
            params.append('lsiSeq', '0');
            params.append('p9', '2,4');
            params.append('p10', classCode);
            params.append('psort', '50');

            const res = await fetch('/lsScListR.do?menuId=1&subMenuId=15&tabMenuId=81', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: params.toString()
            });
            return await res.text();
        }
    """, class_code)

    print(f"  응답 길이: {len(response)}")

    # 감시 키워드가 raw HTML 안에 애초에 있는지부터 확인
    # (여기서 없으면 서버가 애초에 안 내려준 것 — 사이트 자체 분류 문제)
    for kw in WATCH_KEYWORDS:
        found = kw in response
        print(f"  [감시] raw HTML에 '{kw}' 포함 여부: {found}")

    # 디버깅용 저장
    with open("scripts/crawlers/debug_response.html", "w", encoding="utf-8") as f:
        f.write(response)

    # 3. 응답 HTML 파싱
    temp_page = await browser.new_page()
    await temp_page.set_content(response)
    await temp_page.wait_for_timeout(500)

    laws = []
    skipped = []
    items = await temp_page.query_selector_all("li[id^='liBgcolor']")
    total_items = len(items)
    print(f"  li 항목 수: {total_items}")

    for i, item in enumerate(items):
        raw_html = await item.inner_html()
        is_watched = any(kw in raw_html for kw in WATCH_KEYWORDS)

        try:
            link = await item.query_selector("a[onclick*='lsViewWideAll']")
            if not link:
                skipped.append({"index": i, "reason": "link 못 찾음 (a[onclick*=lsViewWideAll] 없음)", "raw_html": raw_html})
                continue

            # 법령명
            span = await link.query_selector("span.tx")
            if not span:
                skipped.append({"index": i, "reason": "span.tx 못 찾음", "raw_html": raw_html})
                continue
            법령명 = (await span.inner_text()).strip()
            # 앞 번호 제거 ("195.  주택임대차보호법" → "주택임대차보호법")
            if "." in 법령명:
                법령명 = 법령명.split(".", 1)[1].strip()

            # onclick에서 MST, 시행일자 추출
            onclick = await link.get_attribute("onclick") or ""
            match = re.search(r"lsViewWideAll\('(\d+)','(\d+)'", onclick)
            if not match:
                skipped.append({
                    "index": i,
                    "reason": f"onclick 정규식 불일치 (onclick 원문: {onclick!r})",
                    "raw_html": raw_html,
                })
                continue
            mst      = match.group(1)
            시행일자 = match.group(2)

            # 법령종류 (tx2에서 추출)
            span2    = await link.query_selector("span.tx2")
            tx2      = (await span2.inner_text()).strip() if span2 else ""
            법령구분 = ""
            if "법률" in tx2:
                법령구분 = "법률"
            elif "대통령령" in tx2:
                법령구분 = "대통령령"
            elif "대법원규칙" in tx2:
                법령구분 = "대법원규칙"
            elif "부령" in tx2 or "령" in tx2:
                법령구분 = "부령"

            if not 법령구분:
                # 법령구분을 못 읽었으면 이후 law_loader.py 필터(법률/대통령령)에서
                # 조용히 걸러질 수 있으니 별도로 표시
                skipped.append({
                    "index": i,
                    "reason": f"법령구분 인식 실패 (tx2 원문: {tx2!r}) — 목록엔 남지만 필터링 시 빠질 위험",
                    "raw_html": raw_html,
                })

            laws.append({
                "법령명":       법령명,
                "MST":          mst,
                "시행일자":     시행일자,
                "법령구분명":   법령구분,
                "법령분류코드": class_code,
                "법령분류명":   class_name,
            })

            if is_watched:
                print(f"  [감시] index={i} 파싱 성공: {법령명} / MST={mst} / 법령구분={법령구분!r}")

        except Exception as e:
            skipped.append({"index": i, "reason": f"예외 발생: {e}", "raw_html": raw_html})
            if is_watched:
                print(f"  [감시] index={i} 예외로 스킵됨: {e}")
                print(f"  [감시] raw_html: {raw_html[:500]}")
            continue

    await temp_page.close()

    print(f"  파싱된 법령 수: {len(laws)}")
    print(f"  스킵된 항목 수: {len(skipped)}  (li 총 {total_items}개 대비)")
    if len(laws) + len(skipped) != total_items:
        print(f"  ⚠️ 카운트 불일치! laws({len(laws)}) + skipped({len(skipped)}) != items({total_items})")

    return laws, skipped


async def main():
    print("=" * 60)
    print("law.go.kr 법령분류별 목록 크롤링")
    print("=" * 60)

    all_laws = {}
    all_skipped = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        for code, name in LAW_CLASS_CODES.items():
            if ACTIVE_CLASSES and code not in ACTIVE_CLASSES:
                continue
            laws, skipped = await fetch_law_list(browser, page, code, name)
            all_laws[name] = laws
            if skipped:
                all_skipped[name] = skipped

        await browser.close()

    output_path = "scripts/crawlers/law_category_list.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_laws, f, ensure_ascii=False, indent=2)

    print(f"\n결과 저장: {output_path}")
    for name, laws in all_laws.items():
        print(f"  {name}: {len(laws)}개")

    if all_skipped:
        skipped_path = "scripts/crawlers/skipped_items_debug.json"
        with open(skipped_path, "w", encoding="utf-8") as f:
            json.dump(all_skipped, f, ensure_ascii=False, indent=2)
        print(f"\n⚠️ 스킵된 항목 {sum(len(v) for v in all_skipped.values())}개 → {skipped_path} 확인 필요")


if __name__ == "__main__":
    asyncio.run(main())