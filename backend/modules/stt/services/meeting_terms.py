"""
같은 회의 시리즈의 이전 회의록에서 용어를 뽑아 컨텍스트에 보탠다 (동적 컨텍스트 Tier 1).

왜 필요한가:
  정적 용어 목록은 "회의에서 나올 단어"를 사람이 미리 예측한 것에 불과하다. 팀마다
  쓰는 단어가 다르고 프로젝트가 진행되며 계속 바뀐다. 그리고 목록을 무한정 늘릴 수도
  없다 — 실측상 목록 길이가 곧 지연이다(204개 0.85초 / 3000개 2.15초).
  **같은 예산으로 그 회의에 맞는 단어를 넣는 것**이 유일한 확장 경로다.

  같은 session_id의 지난 회의에서 나온 단어는 다음 회의에도 나올 확률이 높다.
  이 데이터는 이미 우리가 갖고 있어서 외부 연동 없이 바로 쓸 수 있다.
  (프로젝트 문서·코드에서 뽑는 Tier 2는 맥락을 아는 백엔드가 전달하는 구조로 별도 설계.
   STT가 RAG 저장소를 직접 조회하면 모듈이 결합돼 한쪽 변경이 다른 쪽을 깨뜨린다.)

⚠️ 가장 큰 위험은 오류 되먹임이다:
  1회차에 "임베딩"을 "임베딘"으로 잘못 들으면 → 2회차 용어 목록에 "임베딘"이 들어가고
  → 3회차엔 모델이 그 오답을 더 확신 있게 낸다. 한 번의 오인식이 영구히 굳는다.
  그래서 세 겹으로 막는다:
    ① 사람이 고친 세그먼트(user_edited)는 정답으로 신뢰, 저신뢰(confident=False)는 제외
    ② 정적 목록의 단어와 한두 글자만 다른 것은 오인식 변종으로 보고 제외
       ("임베딘"은 "임베딩"과 편집거리 1 → 버림)
    ③ 여러 회의에 반복 등장한 것을 우선 — 1회성 오인식은 자연히 걸러진다

단독 실행으로 어떤 단어가 뽑히는지 확인할 수 있다:
  python -m stt.services.meeting_terms <session_id>
"""
import json
import os
import re
from collections import Counter, defaultdict

from ..core.config import logger, MEETINGS_DIR

# 한글 2~8음절 또는 영문 대문자 약어. 1음절은 조사와 구분이 안 돼 제외.
_TOKEN = re.compile(r"[가-힣]{2,8}|(?<![A-Za-z])[A-Z][A-Za-z0-9]{1,5}(?![A-Za-z])")

# 조사·어미를 떼어 원형에 가깝게 만든다 (형태소 분석기 없이 하는 근사).
_SUFFIXES = (
    "으로는", "에서는", "이라는", "이라고", "했습니다", "합니다", "입니다", "하는데",
    "으로", "에서", "에게", "하고", "부터", "까지", "처럼", "보다", "라고", "이나",
    "하면", "해서", "해야", "했다", "한다", "이다", "은", "는", "이", "가", "을",
    "를", "의", "에", "와", "과", "도", "만", "로",
)

# 회의 발화에 흔한 일반어. 도메인 용어가 아니므로 힌트로 줄 이유가 없고,
# 넣으면 목록 예산만 잡아먹는다.
_STOP = {
    "그래서", "그리고", "그러면", "그러니까", "하지만", "그런데", "그러나", "따라서",
    "이렇게", "저렇게", "어떻게", "왜냐면", "왜냐하면", "말하자면", "예를", "만약에",
    "생각", "얘기", "이야기", "말씀", "부분", "경우", "정도", "때문", "이유", "방법",
    "지금", "아까", "나중", "먼저", "다음", "이번", "저번", "오늘", "내일", "어제",
    "우리", "저희", "여러분", "본인", "자기", "someone",
    "회의", "논의", "결정", "진행", "확인", "필요", "가능", "문제", "내용", "상황",
    "그거", "이거", "저거", "그것", "이것", "저것", "여기", "거기", "저기",
    "네네", "그쵸", "맞아요", "그렇죠", "알겠습니다", "감사합니다", "죄송합니다",
    "어떤", "무슨", "이런", "저런", "그런", "많이", "조금", "약간", "아주", "정말",
    "해야", "하는", "되는", "있는", "없는", "같은", "같이", "위해", "통해", "대해",
}

# 정적 목록 단어와 이 거리 이하로 가까우면 오인식 변종으로 본다.
_VARIANT_MAX_DISTANCE = 1
_VARIANT_MIN_LEN = 3        # 2음절 단어는 편집거리 1이 흔해 오차단 위험이 크다


def _normalize(token: str) -> str | None:
    if token.isascii():
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            token = token[:-len(suffix)]
            break
    return token if len(token) >= 2 else None


def _edit_distance_at_most(a: str, b: str, limit: int) -> bool:
    """편집거리가 limit 이하인지. 길이 차가 크면 즉시 False (전체 계산 회피)."""
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        if min(cur) > limit:
            return False
        prev = cur
    return prev[-1] <= limit


def _is_variant_of_known(term: str, known: set[str]) -> bool:
    """
    정적 목록 단어의 오인식 변종인지. "임베딘"은 "임베딩"과 한 글자 차이라 버린다.
    이걸 안 막으면 한 번의 오인식이 다음 회의 힌트로 들어가 스스로 강화된다.
    """
    if len(term) < _VARIANT_MIN_LEN:
        return False
    for k in known:
        if k == term or len(k) < _VARIANT_MIN_LEN:
            continue
        if _edit_distance_at_most(term, k, _VARIANT_MAX_DISTANCE):
            return True
    return False


def _iter_past_meetings(session_id: str, exclude_meeting_id: str | None):
    """같은 session_id로 저장된 지난 회의의 transcript.json을 최신순으로."""
    if not os.path.isdir(MEETINGS_DIR):
        return
    prefix = f"{session_id}_"
    names = [n for n in os.listdir(MEETINGS_DIR)
             if n.startswith(prefix) and n != exclude_meeting_id]
    for name in sorted(names, reverse=True):
        path = os.path.join(MEETINGS_DIR, name, "transcript.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                yield name, json.load(f)
        except (OSError, json.JSONDecodeError):
            continue


def collect_session_terms(
    session_id: str,
    known_terms: set[str],
    limit: int = 50,
    max_meetings: int = 10,
    exclude_meeting_id: str | None = None,
) -> list[str]:
    """
    같은 회의 시리즈의 지난 회의록에서 용어 후보를 뽑는다.

    known_terms: 정적 목록. 중복 제거 + 오인식 변종 판정 기준으로 쓴다.
    limit:       뽑을 최대 개수. 목록 길이가 곧 지연이므로 예산을 넘기면 안 된다.
    """
    if not session_id:
        return []

    counts: Counter = Counter()
    meetings_seen: defaultdict = defaultdict(set)
    scanned = 0

    for meeting_id, meta in _iter_past_meetings(session_id, exclude_meeting_id):
        scanned += 1
        if scanned > max_meetings:
            break
        for seg in (meta.get("segments") or []):
            # 사람이 고친 건 정답이 확실하다. 그 외에는 신뢰도가 높은 것만 쓴다 —
            # 저신뢰 구간의 단어를 힌트로 넣으면 오인식을 스스로 강화한다.
            if not (seg.get("user_edited") or seg.get("confident", False)):
                continue
            for raw in _TOKEN.findall(seg.get("text") or ""):
                term = _normalize(raw)
                if not term or term in _STOP or term in known_terms:
                    continue
                counts[term] += 1
                meetings_seen[term].add(meeting_id)

    if not counts:
        return []

    candidates = []
    for term, n in counts.items():
        spread = len(meetings_seen[term])
        # 한 회의에만 나온 단어는 여러 번 나와야 채택 — 1회성 오인식을 거른다.
        if spread < 2 and n < 3:
            continue
        if _is_variant_of_known(term, known_terms):
            logger.debug(f"↩️ 오인식 변종으로 제외: {term}")
            continue
        # 여러 회의에 걸쳐 나온 단어를 우선한다(반복 등장 = 그 팀이 실제로 쓰는 말).
        candidates.append((spread, n, term))

    candidates.sort(reverse=True)
    picked = [t for _, _, t in candidates[:limit]]
    if picked:
        logger.info(
            f"📚 [{session_id}] 지난 회의 {scanned}건에서 용어 {len(picked)}개 수집: "
            f"{', '.join(picked[:8])}{' …' if len(picked) > 8 else ''}"
        )
    return picked


if __name__ == "__main__":
    import sys
    from ..core.config import QWEN_CONTEXT_TERMS

    if len(sys.argv) < 2:
        raise SystemExit("사용법: python -m stt.services.meeting_terms <session_id> [limit]")
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    terms = collect_session_terms(sys.argv[1], set(QWEN_CONTEXT_TERMS), limit=limit)
    print(f"\n수집된 용어 {len(terms)}개:")
    for t in terms:
        print(f"  {t}")
