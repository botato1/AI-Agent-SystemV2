"""
scripts/crawlers/law_kind_crawler.py
law.go.kr 법령종류별(법률/대통령령) 전체 목록 크롤링

[기존 law_category_crawler.py와의 차이]
    기존: p10(법령분류코드, 예: 08=민사법) 기준으로 카테고리 안에서만 수집
          → 공인중개사법처럼 해당 카테고리 밖에 있는 법이 누락됨
    수정: p1(법령종류코드, 예: 10002=법률) 기준으로 수집, p10은 아예 안 보냄
          → 법령분류(민사법/형사법 등)에 상관없이 "법률" 또는 "대통령령"
            전체를 빠짐없이 수집 (공인중개사법도 여기 포함됨)

    법령종류 코드는 브라우저 Network 탭에서 실측 확인함:
        법률     → p1=10002
        대통령령 → p1=10007

실행:
    python scripts/crawlers/law_kind_crawler.py
"""

import re
import json
import asyncio
from playwright.async_api import async_playwright

SEARCH_URL = "https://law.go.kr/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query="

# 법령종류 코드 (브라우저 Network 탭에서 실측 확인)
LAW_KIND_CODES = {
    "10002": "법률",
    "10007": "대통령령",
}

WATCH_KEYWORDS = ["공인중개사법"]


async def fetch_law_list(browser, page, kind_code: str, kind_name: str) -> tuple[list[dict], list[dict]]:
    print(f"\n[{kind_name}(p1={kind_code})] 목록 수집 중...")

    await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(2000)

    response = await page.evaluate("""
        async (kindCode) => {
            const params = new URLSearchParams();
            params.append('q', '*');
            params.append('outmax', '9999');   // 화면 기본값 50 → 전체 수집 위해 늘림
            params.append('p1', kindCode);     // 법령종류 코드 (10002=법률, 10007=대통령령)
            params.append('p18', '0');
            params.append('p19', '1,3');
            params.append('pg', '1');
            params.append('fsort', '80,10');
            params.append('lsType', 'null');
            params.append('section', 'lawNm');
            params.append('lsiSeq', '0');
            params.append('p9', '2,4');
            // 주의: p10(법령분류코드)는 의도적으로 안 보냄
            //       → 특정 분류(민사법 등)에 갇히지 않고 전체 수집

            const res = await fetch('/lsScListR.do?menuId=1&subMenuId=15&tabMenuId=81', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: params.toString()
            });
            return await res.text();
        }
    """, kind_code)

    print(f"  응답 길이: {len(response)}")
    for kw in WATCH_KEYWORDS:
        print(f"  [감시] raw HTML에 '{kw}' 포함 여부: {kw in response}")

    with open(f"scripts/crawlers/debug_response_{kind_code}.html", "w", encoding="utf-8") as f:
        f.write(response)

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
        try:
            link = await item.query_selector("a[onclick*='lsViewWideAll']")
            if not link:
                skipped.append({"index": i, "reason": "link 없음", "raw_html": raw_html})
                continue

            span = await link.query_selector("span.tx")
            if not span:
                skipped.append({"index": i, "reason": "span.tx 없음", "raw_html": raw_html})
                continue
            법령명 = (await span.inner_text()).strip()
            if "." in 법령명:
                법령명 = 법령명.split(".", 1)[1].strip()

            onclick = await link.get_attribute("onclick") or ""
            match = re.search(r"lsViewWideAll\('(\d+)','(\d+)'", onclick)
            if not match:
                skipped.append({"index": i, "reason": f"onclick 불일치: {onclick!r}", "raw_html": raw_html})
                continue
            mst      = match.group(1)
            시행일자 = match.group(2)

            span2 = await link.query_selector("span.tx2")
            tx2   = (await span2.inner_text()).strip() if span2 else ""
            법령구분 = ""
            if "법률" in tx2:
                법령구분 = "법률"
            elif "대통령령" in tx2:
                법령구분 = "대통령령"
            elif "대법원규칙" in tx2:
                법령구분 = "대법원규칙"
            elif "부령" in tx2 or "령" in tx2:
                법령구분 = "부령"

            laws.append({
                "법령명":       법령명,
                "MST":          mst,
                "시행일자":     시행일자,
                "법령구분명":   법령구분 or kind_name,  # tx2 파싱 실패해도 요청 기준값으로 fallback
            })

        except Exception as e:
            skipped.append({"index": i, "reason": f"예외: {e}", "raw_html": raw_html})
            continue

    await temp_page.close()

    print(f"  파싱된 법령 수: {len(laws)}")
    print(f"  스킵된 항목 수: {len(skipped)} (li 총 {total_items}개 대비)")
    if len(laws) + len(skipped) != total_items:
        print(f"  ⚠️ 카운트 불일치! laws({len(laws)}) + skipped({len(skipped)}) != items({total_items})")

    return laws, skipped


async def main():
    print("=" * 60)
    print("law.go.kr 법령종류별(법률/대통령령) 전체 목록 크롤링")
    print("=" * 60)

    all_laws = {}
    all_skipped = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        for code, name in LAW_KIND_CODES.items():
            laws, skipped = await fetch_law_list(browser, page, code, name)
            all_laws[name] = laws
            if skipped:
                all_skipped[name] = skipped

        await browser.close()

    output_path = "scripts/crawlers/law_kind_list.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_laws, f, ensure_ascii=False, indent=2)

    print(f"\n결과 저장: {output_path}")
    for name, laws in all_laws.items():
        print(f"  {name}: {len(laws)}개")
        names_only = {law["법령명"] for law in laws}
        for kw in WATCH_KEYWORDS:
            print(f"    [감시] '{kw}' 포함 여부: {kw in names_only}")

    if all_skipped:
        skipped_path = "scripts/crawlers/skipped_items_debug.json"
        with open(skipped_path, "w", encoding="utf-8") as f:
            json.dump(all_skipped, f, ensure_ascii=False, indent=2)
        print(f"\n⚠️ 스킵된 항목 있음 → {skipped_path} 확인")


if __name__ == "__main__":
    asyncio.run(main())