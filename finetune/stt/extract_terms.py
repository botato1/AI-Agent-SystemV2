"""
컨텍스트 바이어싱용 용어 목록을 텍스트 코퍼스에서 자동 추출.

왜 자동 추출인가:
  기존 목록(terms_context.txt 68개)은 사람이 손으로 적은 것이라 "회의에서 나올 단어"를
  예측한 것에 불과하다. 목록을 늘리려면 근거가 있어야 하고, 손으로 300개를 적는 건
  지속 가능하지도 않다.

무엇을 노리는가:
  STT가 틀리는 건 대부분 **외래어 표기 기술 용어**다(임베딩, 웹소켓, 파인튜닝, 컨테이너).
  순수 한국어(서버, 개발, 회의)는 애초에 잘 맞히므로 목록에 넣을 이유가 없다 —
  오히려 목록이 길어지면 말하지 않은 단어를 끌어오는 오적용 위험만 커진다
  (실측 사례: "저번 프로젝트" → "저번 풀리퀘스트").

어떻게 고르는가:
  기술 코퍼스(--tech)와 일반 코퍼스(--general)의 상대 빈도를 비교한다.
  기술 쪽에서 자주 나오는데 일반 쪽에는 드문 단어가 곧 도메인 전문용어다.
  일반 회의에서도 흔한 단어는 걸러진다 — 그런 단어는 힌트를 줄 이유가 없다.

사용법:
  python extract_terms.py --tech ../../backend --general ../../data/test_meetings --top 300
  python extract_terms.py ... --output ../../backend/modules/stt/core/terms_context.txt
"""
import argparse
import os
import re
from collections import Counter

# 한글 2~8음절 또는 영문 대문자 약어(2~6자). 조사가 붙기 쉬운 1음절은 제외한다.
_TOKEN = re.compile(r"[가-힣]{2,8}|(?<![A-Za-z])[A-Z][A-Za-z0-9]{1,5}(?![A-Za-z])")

# 조사·어미가 붙은 형태를 원형으로 되돌리기 위한 접미사 (긴 것부터)
_SUFFIXES = (
    "으로는", "에서는", "이라는", "이라고", "하는데", "합니다", "했습니다", "입니다",
    "으로", "에서", "에게", "이랑", "하고", "부터", "까지", "처럼", "보다", "라고",
    "하면", "해서", "해야", "했다", "한다", "이다", "이나", "은", "는", "이", "가",
    "을", "를", "의", "에", "와", "과", "도", "만", "로", "년", "월", "일",
)

# 형태소 분석기 없이 접미사만 떼면 남는 흔한 비명사 어간·부사. 도메인과 무관하게 자주 나온다.
_STOP = {
    "그리고", "그래서", "하지만", "그러면", "그러니까", "이렇게", "저렇게", "어떻게",
    "때문", "경우", "부분", "정도", "이후", "이전", "지금", "우리", "여기", "거기",
    "가지", "생각", "확인", "필요", "사용", "적용", "처리", "동작", "실행", "설정",
    "문제", "결과", "방식", "방법", "이유", "상태", "기준", "대상", "관련", "내용",
    "수정", "추가", "제거", "변경", "구현", "테스트", "코드", "파일", "함수", "값",
    # 접미사 제거 후 남는 조사·연결어. 도메인과 무관한데 빈도가 높아 상위를 차지한다.
    "에서", "으로", "에게", "이랑", "하고", "부터", "까지", "처럼", "보다", "라고",
    "하면", "해서", "해야", "이나", "이런", "저런", "그런", "여러", "각각", "모두",
    "다시", "먼저", "바로", "아직", "이미", "항상", "직접", "실제", "가장", "매우",
    # 일반 동작·상태 명사. 기술 문서에 흔하지만 STT가 틀리는 단어가 아니다.
    "등록", "완료", "시작", "종료", "반환", "호출", "전달", "저장", "생성", "삭제",
    "추출", "변환", "자동", "수동", "기본", "옵션", "목록", "경로", "모드", "정보",
    "구간", "단위", "기능", "동일", "포함", "제외", "이상", "이하", "미만", "초과",
    "만약", "해당", "위해", "통해", "따라", "대해", "관해", "역시", "물론", "다만",
}


def read_corpus(paths: list[str]) -> str:
    """
    디렉터리면 재귀적으로 읽어 텍스트를 이어붙인다.

    소스 파일에서는 **한글이 들어간 줄만** 취한다. 코드 본문을 그대로 읽으면
    식별자(None, BASE_DIR, Path…)가 용어 후보로 올라와 목록을 오염시킨다.
    우리가 원하는 건 사람이 쓴 한글 주석·문서에 나오는 도메인 어휘다.
    """
    exts = (".py", ".md", ".txt", ".ts", ".tsx", ".js", ".html")
    chunks: list[str] = []
    for path in paths:
        files = []
        if os.path.isdir(path):
            for root, dirs, names in os.walk(path):
                dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".git")]
                files += [os.path.join(root, n) for n in names if n.endswith(exts)]
        elif os.path.isfile(path):
            files = [path]
        for f in files:
            try:
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if re.search(r"[가-힣]", line):
                            chunks.append(line)
            except OSError:
                continue
    return "".join(chunks)


def normalize(token: str) -> str | None:
    """조사·어미를 떼어 원형에 가깝게. 너무 짧아지면 버린다."""
    if token.isascii():
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            token = token[:-len(suffix)]
            break
    return token if len(token) >= 2 else None


def count(text: str) -> Counter:
    counter: Counter = Counter()
    for raw in _TOKEN.findall(text):
        token = normalize(raw)
        if token and token not in _STOP:
            counter[token] += 1
    return counter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tech", nargs="+", required=True,
                        help="기술 코퍼스 (레포 소스/문서 디렉터리)")
    parser.add_argument("--general", nargs="+", required=True,
                        help="일반 코퍼스 (일상 업무 회의 텍스트 등) — 대조군")
    parser.add_argument("--top", type=int, default=300, help="뽑을 용어 수")
    parser.add_argument("--min-count", type=int, default=5, help="기술 코퍼스 최소 등장 횟수")
    parser.add_argument("--output", default=None, help="저장 경로 (미지정 시 화면 출력만)")
    args = parser.parse_args()

    tech = count(read_corpus(args.tech))
    general = count(read_corpus(args.general))
    tech_total = max(sum(tech.values()), 1)
    general_total = max(sum(general.values()), 1)

    # 도메인 특이도 = 기술 코퍼스 상대빈도 / 일반 코퍼스 상대빈도.
    # 일반 코퍼스에 없는 단어는 분모를 아주 작은 값으로 둬서 높은 점수를 받게 한다.
    scored = []
    for term, n in tech.items():
        if n < args.min_count:
            continue
        p_tech = n / tech_total
        p_general = general.get(term, 0) / general_total
        specificity = p_tech / (p_general + 1e-7)
        scored.append((specificity, n, term))

    scored.sort(reverse=True)
    picked = scored[:args.top]

    print(f"기술 코퍼스   : {tech_total:,} 토큰 / 고유 {len(tech):,}")
    print(f"일반 코퍼스   : {general_total:,} 토큰 / 고유 {len(general):,}")
    print(f"후보(≥{args.min_count}회): {len(scored):,} → 상위 {len(picked)}개 선정\n")

    print(f"{'용어':<18s}{'등장':>6s}{'특이도':>10s}")
    for spec, n, term in picked[:40]:
        print(f"{term:<18s}{n:>6d}{spec:>10.1f}")
    if len(picked) > 40:
        print(f"... 외 {len(picked) - 40}개")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("# 컨텍스트 바이어싱 용어 목록 — extract_terms.py 자동 생성\n")
            f.write(f"# 기술 코퍼스: {', '.join(args.tech)}\n")
            f.write(f"# 일반 코퍼스(대조군): {', '.join(args.general)}\n")
            f.write(f"# 상위 {len(picked)}개 (도메인 특이도 순, 최소 {args.min_count}회 등장)\n")
            f.write("#\n")
            f.write("# ⚠️ 목록이 길수록 말하지 않은 단어를 끌어오는 오적용 위험이 커진다.\n")
            f.write("#    크기를 바꿨으면 AI-Hub held-out(개발 용어가 없는 데이터)으로\n")
            f.write("#    CER 회귀를 반드시 확인할 것 — 거기서 나빠지면 오적용이 생긴 것이다.\n\n")
            for _, _, term in picked:
                f.write(term + "\n")
        print(f"\n저장: {args.output}")


if __name__ == "__main__":
    main()
