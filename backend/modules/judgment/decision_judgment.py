"""실시간 판단 파이프라인 1-1: 결정 비교 판단 (통합)

결정 리마인더 / 근거 명확한 변경 / 근거 불명확한 변경, 이 세 기능은 별개가 아니라
하나의 판단 파이프라인이 결과에 따라 갈라진 것이다 (설계 문서 1-1 참조).

핵심 원칙 — "이미 결정된 걸 다르게 말하는 것 = 변경 후보":
발화가 새로운 값/입장을 제시하는가(→ 값 비교로), 아니면 주제만 재언급하는가
(→ 리마인더)를 먼저 가른다. 재확인이 "글자 그대로 같을 때만"으로 좁아지는 걸
피하기 위함.

3단계 판단 (전부 Model1 단일 파인튜닝 모델을 배치별 instruction으로 순차 호출):
  1단계) 새 값 제시 여부   → 아니오: Case 0(리마인더)
  2단계) 값이 기존과 같은가 → 예: Case 1(무시)
  3단계) 근거가 명확한가   → 예: Case 2(명확한 근거의 변경) / 아니오: Case 3(명확한 근거 없이 변경)

[수정 - 2026.07.27] confidence/Model2 이원화 및 Case 4(보류·반복카운트) 제거.
Case 4는 세션 카운트 기반으로 재설계해서 별도로 다시 넣을 예정 - 지금은 없음.

[수정] 카테고리 내 active decision 전체를 topic_match로 판단하던 것(벡터 검색
완전 제거)을 되돌림 - decision이 쌓일수록 발화 1개당 LLM 호출이 선형으로 늘어나
느려지는 문제가 있었음. 벡터 검색을 "필터"가 아니라 "후보 축소"로만 앞단에 둔다
(임계값을 낮게 잡아 진짜 매칭이 후보 밖으로 밀리는 걸 방지, 최종 판단은 여전히
topic_match가 함).

[수정] Case 2/3는 "모순"이 아니라 "결정 변경"으로 명명한다 - 문서 내용과의
충돌(document_judgment)과는 성격이 달라, 근거 명확성 기준으로
reasoned_change/unreasoned_change로 구분한다. 팝업은 세션 내 (decision, case)
단위로 1회만 뜨지만, contradictions row는 매번 생성되어 post-meeting이 세션 내
최신 행을 그대로 사용자 확인 대상으로 재사용할 수 있게 한다 (전체 회의를 다시
읽고 재판단하지 않음 - decision_transition.py 참조).
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.db.crud import contradiction_crud, history_crud
from backend.db.modules import Decision, Meeting
from backend.modules.llm.ollama_client import _call_ollama
from backend.modules.rag import chroma_client

# [수정 - 2026.07.27] confidence/Model2 이원화 제거. 판단은 배치1~4 통합
# 파인튜닝 모델(re-call-model1-unified-v7) 하나로, 단계별 개별 호출.
# ollama_client.OLLAMA_MODEL_LIGHT를 그대로 안 쓰는 이유: 그건 의도분류/일반답변
# 등 다른 기능도 같이 쓰는 공용 상수라, 판단 전용 모델을 거기 넣으면 다른 기능까지
# 좁은 판단용 모델로 넘어가게 됨 - 판단 파이프라인 전용 상수를 따로 둔다.
#
# [수정 - 2026.08.20] v7 -> v12로 기본값 변경. topic_match 홀드아웃에서 v12가
# v15보다 안정적이라 실사용 모델로 v12 확정(end-to-end 종합 점수는 v15가 더
# 높지만, topic_match가 판단 파이프라인의 첫 관문이라 실사용 리스크를 우선
# 낮춤 - 상세 경위는 memory:project_recall_v2_next_roadmap 참조). .env의
# OLLAMA_MODEL_JUDGMENT가 항상 우선하지만, 이 기본값 자체도 "옛날 모델(v7)"로
# 조용히 폴백되는 걸 막기 위해 실사용 모델로 맞춰둔다.
# TODO: v12 양자화(v12-q4) blob 등록 마무리되면 기본값을 v12-q4로 다시 교체할 것
# (BF16 대비 정확도 손실 없이 토큰 생성 속도 약 2배 이상 빨라짐, v7-q4에서 검증됨).
JUDGMENT_MODEL = os.getenv("OLLAMA_MODEL_JUDGMENT", "re-call-model1-unified-v12")

# [수정 - 2026.08.03] threshold=0.3은 실회의록 스모크테스트(data/test_meetings/)에서
# 결정 개수가 적은 워크스페이스일 때 "넵 알겠습니다" 같은 무관한 발화까지 거의 항상
# 후보로 통과시키는 것을 확인함(dense count == final count로 사실상 무필터). 후보
# narrowing이 안 되면 topic_match 잔여 오류율(홀드아웃 기준 8~10%)이 후보 개수만큼
# 곱해져 노출됨 - 0.5로 올려 실제 필터 역할을 하게 함(TBD - 추후 대규모 실측 후 재조정).
DECISION_CANDIDATE_TOP_K = int(os.getenv("DECISION_CANDIDATE_TOP_K", "15"))
DECISION_CANDIDATE_THRESHOLD = float(os.getenv("DECISION_CANDIDATE_THRESHOLD", "0.4"))

# [수정 - 리뷰 반영] 벡터 후보(top-15)를 전부 topic_match로 순회하면 무관한 발화 하나당
# 최악의 경우 LLM 호출이 15번까지 순차로 늘어나 체감 지연이 커짐. 후보는 이미 벡터
# 점수 순 정렬이므로, 상위 몇 개까지만 topic_match로 확인하고 그 안에서 못 찾으면
# "none"으로 처리한다 (TBD - 실측 후 조정).
TOPIC_MATCH_MAX_ATTEMPTS = int(os.getenv("TOPIC_MATCH_MAX_ATTEMPTS", "5"))

# 배치1~3 학습 때 쓴 instruction 그대로 - 문구가 조금이라도 다르면 정확도가 크게 떨어짐
JUDGMENT_STEP_INSTRUCTIONS = {
    "presents_new_value": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화가 새로운 값/입장을 제시하는지, "
        "아니면 단순히 과거 결정을 재언급/질문하는 것인지만 판단해서 JSON으로만 답하라."
    ),
    "same_as_existing": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화는 이미 새로운 값/입장을 제시하고 있다. "
        "그 값이 기존 결정과 실질적으로 같은 내용인지 다른 내용인지만 판단해서 JSON으로만 답하라."
    ),
    "reason_is_clear": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화는 이미 기존 결정과 다른 새 값을 제시하고 있다. "
        "왜 바뀌는지 근거/이유가 발화 안에 명확하게 드러나 있는지만 판단해서 JSON으로만 답하라."
    ),
}

JUDGMENT_INPUT_TEMPLATE = """[과거 결정]
{decision_text}
(결정 이유: {decision_reason})

[방금 발화]
{statement}"""

# 배치4(topic_match) v7 학습 때 쓴 instruction 그대로 - 문구가 조금이라도
# 다르면 정확도가 크게 떨어짐 (finetune/dataset_topic_match_v2_augment.jsonl 참조).
# 학습 데이터의 instruction 필드는 JSON 출력 스펙까지 안에 포함돼 있으므로,
# 이 상수도 스펙을 끝에 그대로 포함해서 학습 형식과 완전히 동일하게 맞춘다
# (아래 _ask_topic_match()에서 별도로 스펙을 덧붙이지 않는 이유이기도 함).
TOPIC_MATCH_INSTRUCTION = (
    "아래는 과거 의사결정과 새 발화이다.\n\n"
    "목표:\n새 발화가 과거 의사결정에서 실제로 결정된 그 항목·속성을 다루는지 판단하라.\n\n"
    "같은 주제(true)인 경우\n"
    "- 과거 의사결정에서 선택한 항목을 다른 기술/서비스/제품으로 교체하자는 제안\n"
    "- 과거 의사결정에서 정한 그 설정값(수치, 기간, 비율, 개수 등)을 조정하자는 제안\n"
    "- 과거 의사결정과 동일한 선택지를 놓고 대안을 비교하거나 장단점을 논하는 경우\n"
    "- 과거 의사결정 내용 자체를 단순히 되묻거나 재확인하거나 다시 언급하는 경우, "
    "변경 의도가 없는 동의·긍정적 코멘트도 포함\n"
    "  (예: \"그거 A로 하기로 했었죠?\", \"왜 A로 정했었죠\", \"A 맞나요\", "
    "\"A로 그대로 가면 될 것 같아요\", \"A가 요즘 보니 괜찮더라고요\")\n\n"
    "다른 주제(false)인 경우\n"
    "- 같은 시스템/프로젝트/컴포넌트에 대한 이야기라도, 과거 의사결정이 실제로\n"
    "  다루지 않은 별개의 속성·정책·운영 이슈인 경우\n"
    "  (예: \"DB는 PostgreSQL을 쓴다\"는 \"어떤 DB 기술을 쓸지\"에 대한 결정이므로,\n"
    "  같은 DB에 대한 이야기여도 \"백업 주기\", \"마이그레이션 자동화\" 등은 별개 항목)\n"
    "- 비슷한 분야/카테고리라도 역할이 다른 경우 (예: 관계형DB vs 벡터DB, "
    "인증 vs 권한관리, 캐시 vs 메시지큐, 검색엔진 vs 그래프DB) — 배경지식으로 "
    "역할이 다름을 판단해야 하는 경우도 포함\n"
    "- 기존 결정과 독립적인 신규 기능 또는 신규 컴포넌트 제안\n"
    "- 완전히 무관한 화제\n\n"
    "판단의 핵심은 \"같은 시스템/키워드가 언급되었는가\"가 아니라\n"
    "\"과거에 실제로 결정된 바로 그 속성을 다루는가\"이다.\n\n"
    "다음 JSON만 출력한다.\n{\n  \"reason\": \"20자 이내\",\n  \"same_topic\": true | false\n}"
)

TOPIC_MATCH_INPUT_TEMPLATE = """[과거 의사결정]
{decision_text}
(결정 이유: {decision_reason})

[새 발화]
{statement}"""


def _ask_judgment_step(key: str, decision_text: str, decision_reason: str, statement: str) -> bool:
    """JUDGMENT_MODEL에게 단계 하나(key)만 물어서 bool로 반환. 실패 시 False.

    [수정] temperature=0 명시 - 기본값(Ollama 기본 0.8 근처)이면 완전히 같은 발화를
    두 번 판단시켜도 결과가 달라질 수 있다. 특히 STT가 같은 구간에 대해 "final"을
    중복으로 보내는 경우(세그먼트 저장 쪽엔 중복 방지가 없음), 두 번째 판단이
    첫 번째와 다른 case로 나오면서 서로 다른 팝업이 중복으로 뜨는 문제가 있었다.
    temperature=0이면 같은 입력→같은 출력이 보장되어, 기존 dedup(같은 decision·
    같은 case면 세션당 1회)이 정상적으로 두 번째를 걸러준다.
    """
    input_text = JUDGMENT_INPUT_TEMPLATE.format(
        decision_text=decision_text, decision_reason=decision_reason, statement=statement,
    )
    prompt = (
        f"{JUDGMENT_STEP_INSTRUCTIONS[key]}\n\n{input_text}\n\n"
        f'반드시 다음 JSON 형식으로만 답하라 (다른 설명 금지):\n{{\n  "{key}": true/false\n}}'
    )
    raw = _call_ollama(prompt, timeout=60.0, model=JUDGMENT_MODEL, temperature=0)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return False
        parsed = json.loads(raw[start : end + 1])
        return bool(parsed.get(key, False))
    except (json.JSONDecodeError, ValueError):
        return False


def _ask_topic_match(decision_text: str, decision_reason: str, statement: str) -> bool:
    """후보 decision과 발화가 실제로 같은 의사결정을 수정하려는 건지 topic_match로 검증."""
    input_text = TOPIC_MATCH_INPUT_TEMPLATE.format(
        decision_text=decision_text, decision_reason=decision_reason, statement=statement,
    )
    # TOPIC_MATCH_INSTRUCTION이 이미 JSON 출력 스펙을 끝에 포함하고 있으므로
    # (학습 데이터의 instruction 필드와 동일한 형식), 여기서 별도로 스펙을
    # 덧붙이지 않는다 - instruction 뒤에 input만 붙이는 게 학습 형식과 일치한다.
    prompt = f"{TOPIC_MATCH_INSTRUCTION}\n\n{input_text}"
    # temperature=0 명시 이유는 _ask_judgment_step() 주석 참조 - 같은 입력에는
    # 항상 같은 판단이 나와야 dedup이 제대로 동작한다.
    #
    # [수정 - 리뷰 반영] _call_ollama() 호출이 try 밖에 있어서 네트워크/타임아웃 등
    # httpx 예외가 그대로 던져지던 버그. _extract_change_reason()이 겪었던 것과 동일한
    # 패턴 - decision_transition.py가 이 함수를 topic 1개당 최대 5회까지 호출하게
    # 되면서 (해당 파일의 process_topics() 루프엔 try/except가 없음) 예외가
    # meeting_postprocess_node의 최상위 except까지 전파되어 회의 후처리 전체(요약·
    # 모든 결정사항·모든 할 일)가 실패 처리되는 문제로 이어질 수 있어 수정.
    try:
        raw = _call_ollama(prompt, timeout=60.0, model=JUDGMENT_MODEL, temperature=0)
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return False
        parsed = json.loads(raw[start : end + 1])
        return bool(parsed.get("same_topic", False))
    except Exception as e:
        print(f"[decision_judgment] topic_match 실패, 매칭 안 된 것으로 보수적 처리: {repr(e)}")
        return False


# [추가 - 리뷰 반영, 2026.08.10] Case 2 팝업의 "이유" 필드 버그 수정용.
# create_contradiction()에 reason=decision.reason(기존 결정의 사유)을 그대로
# 넘기고 있었는데, 이건 "왜 예전에 그렇게 정했는지"지 "왜 지금 바뀌는지"가
# 아님 - 기존 결정에 사유가 없으면 근거가 명확히 확인된 Case 2인데도 "사유
# 미기재"로 뜨고, 있어도 다른 필드(기존 내용)와 내용이 겹쳐 보였음.
# reason_is_clear 판단 단계는 bool만 반환하므로, 근거가 명확하다고 판단된
# 경우(Case 2)에만 별도로 그 근거 텍스트 자체를 짧게 추출한다.
#
# [수정 - 2026.08.12 라이브 테스트 발견] statement가 단독 발화 하나뿐이라 실제
# 근거는 다른 화자의 이전 turn에 있고 이 발화 자체엔 근거가 없는 경우, 기존
# instruction이 "발화가 근거를 담고 있다"고 단정해서 물어봐서 LLM이 없는 근거를
# 지어내는(할루시네이션) 문제가 실측으로 확인됨 (예: "리랭킹은 보류하고 질의
# 확장을 먼저 넣는 걸로 확정하겠습니다"만 보고 대본에 없는 "질문 분야가
# 명확해져 처리가 용이해서"를 만들어냄). "언급하고 있다면"으로 전제를 완화하고,
# 근거가 실제로 없으면 지어내지 말고 원문을 그대로 반환하라는 탈출구를 명시.
REASON_EXTRACT_INSTRUCTION = (
    "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화가 기존 결정과 다른 새 값을 "
    "제시하면서 왜 바뀌는지 근거/이유도 명시적으로 언급하고 있다면, 그 부분만 "
    "간결하게(20자 내외) 추출하라. 근거가 여러 개면 핵심만 요약하라. "
    "발화 안에 근거가 실제로 언급되어 있지 않다면 절대로 지어내지 말고, "
    "반드시 발화 원문을 그대로 반환하라."
)

REASON_EXTRACT_INPUT_TEMPLATE = """[발화]
{statement}"""


def _extract_change_reason(statement: str) -> str:
    """Case 2(근거 명확)로 판단된 발화에서 근거 텍스트만 짧게 추출.
    실패 시 발화 원문을 그대로 반환(빈 값보다는 원문이 나음 - 최소한 근거가
    포함된 전체 맥락은 보여줄 수 있음).

    [수정 - 리뷰 반영] _call_ollama() 호출까지 try 안으로 넣고 except를
    Exception으로 넓힘. 원래는 JSON 파싱 실패만 잡고 있었는데, _call_ollama()
    자체는 내부에 try/except가 없어 네트워크/타임아웃 시 httpx 예외를 그대로
    던진다 - 이 호출부가 try 밖에 있으면 그 예외가 judge() -> run_judgment_
    pipeline()의 최상위 except까지 안 잡히고 올라가서, 이미 끝난 Case 2 감지
    자체(create_contradiction 호출 전)가 통째로 유실된다. 근거 추출은 부가
    정보일 뿐이므로, 어떤 이유로 실패하든 원문 폴백으로 안전하게 넘어가야 한다.
    """
    input_text = REASON_EXTRACT_INPUT_TEMPLATE.format(statement=statement)
    prompt = (
        f"{REASON_EXTRACT_INSTRUCTION}\n\n{input_text}\n\n"
        f'반드시 다음 JSON 형식으로만 답하라 (다른 설명 금지):\n{{\n  "reason": "..."\n}}'
    )
    try:
        raw = _call_ollama(prompt, timeout=60.0, model=JUDGMENT_MODEL, temperature=0)
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return statement
        parsed = json.loads(raw[start : end + 1])
        reason = parsed.get("reason")
        return reason.strip() if isinstance(reason, str) and reason.strip() else statement
    except Exception as e:
        print(f"[decision_judgment] 근거 추출 실패, 원문으로 폴백: {repr(e)}")
        return statement


# [추가 - 리뷰 반영] Case 0/2/3 메시지에 decision.decided_at(datetime)을 그대로
# f-string에 넣으면 마이크로초(.831488)/타임존 오프셋(+00:00)까지 그대로
# 노출된다. 이 메시지가 popup["message"]로 Notification 저장용과 WS push용
# 양쪽에 동일하게 재사용되므로, 포맷 함수 하나로 통일해서 앞으로 이런
# 불일치가 다시 안 생기게 한다.
#
# [수정 - 리뷰 반영] decided_at은 DateTime(timezone=True) 컬럼에 UTC로
# 저장됨(decision_transition.py가 datetime.now(timezone.utc) 사용). 변환 없이
# 바로 strftime하면 KST 새벽 0~9시 사이에 결정된 항목은 날짜가 하루 전으로
# 잘못 표시됨 - astimezone(KST) 거친 뒤 포맷하도록 수정.
KST = timezone(timedelta(hours=9))


def _format_decided_at(decided_at) -> str:
    if decided_at is None:
        return "날짜 미상"
    return decided_at.astimezone(KST).strftime("%Y-%m-%d")


# [추가 - 팀 결정] Case 0(재확인/질문)과 Case 1(새 값처럼 말했지만 사실상 기존
# 결정과 동일)은 둘 다 "이미 이렇게 결정된 이력이 있다"는 같은 성격의 FYI라,
# 같은 decision_reminder 팝업을 공유한다. 세션당 1회 dedup도 case 구분 없이
# reference_decision_id 하나로 공유 - 어느 쪽이 먼저 뜨든 같은 문구가 두 번
# 뜨는 건 의미가 없으므로 의도된 동작이다.
def _decision_reminder_result(
    db: Session, *, case: str, workspace_id: uuid.UUID, category_id: uuid.UUID,
    source_type: str, decision: "Decision", session_kwargs: dict,
) -> dict:
    already_shown = history_crud.already_notified_in_session(
        db, reference_decision_id=decision.id, **session_kwargs
    )
    if already_shown:
        return {"case": case, "popup": None, "decision_id": str(decision.id)}

    history_crud.record_match(
        db,
        workspace_id=workspace_id, category_id=category_id,
        source_type=source_type, match_type="decision_reminder",
        reference_decision_id=decision.id,
        confidence_score=1.0,  # 벡터 점수 대신 topic_match가 이미 같은 주제로 확정한 것이라 고정값
        **session_kwargs,
    )
    return {
        "case": case,
        "popup": {
            "type": "decision_reminder",
            "message": f"이미 '{decision.decision_text}'로 결정된 이력이 있습니다"
                       f" ({_format_decided_at(decision.decided_at)}, {decision.reason or '사유 미기재'})",
        },
        "decision_id": str(decision.id),
    }


def _get_candidate_decisions(
    db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, statement: str
) -> list[Decision]:
    """벡터 검색으로 후보를 먼저 좁힌 뒤, topic_match는 그 후보에 대해서만 돈다.
    [수정] active decision 전체를 매번 topic_match하면 decision이 쌓일수록
    발화 1개당 LLM 호출이 선형으로 늘어 느려짐 - 벡터 검색을 "필터"가 아니라
    "후보 축소"용으로 다시 앞단에 둔다. threshold를 낮게 잡아 임베딩이 약한
    진짜 매칭도 후보에서 안 빠지게 한다. Decision엔 category_id가 없어
    Meeting을 조인한다."""
    results = chroma_client.search_hybrid(
        query_text=statement,
        workspace_id=str(workspace_id),
        category_id=str(category_id),
        top_k=DECISION_CANDIDATE_TOP_K,
        collection_name=chroma_client.DECISION_COLLECTION,
    )
    candidate_ids = [
        uuid.UUID(r["document_id"]) for r in results
        if r.get("document_id") and r["score"] >= DECISION_CANDIDATE_THRESHOLD
    ]
    if not candidate_ids:
        return []

    decisions = (
        db.query(Decision)
        .join(Meeting, Decision.meeting_id == Meeting.id)
        .filter(
            Decision.id.in_(candidate_ids),
            Meeting.category_id == category_id,
            Decision.workspace_id == workspace_id,
            Decision.status == "active",
            Decision.deleted_at.is_(None),
        )
        .all()
    )
    order = {cid: i for i, cid in enumerate(candidate_ids)}
    decisions.sort(key=lambda d: order.get(d.id, len(order)))  # 벡터 점수 순서 유지
    return decisions


def judge(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    source_type: str,  # 'meeting_segment' | 'room_message'
    source_id: uuid.UUID,
    statement: str,
    session_meeting_id: uuid.UUID | None = None,
    session_room_id: uuid.UUID | None = None,
) -> dict:
    """
    발화 하나를 받아 1-1 판단을 수행한다.

    Returns:
        {"case": "none"|"0"|"1"|"2"|"3", "popup": dict|None, "decision_id": str|None}
        popup은 팝업을 띄워야 하면 {"type": ..., "message": ...} 형태, 아니면 None.
        "none"은 관련 있는 active decision이 없어 1-2로 넘겨야 함을 의미.
    """
    candidates = _get_candidate_decisions(db, workspace_id, category_id, statement)

    decision = None
    for candidate in candidates[:TOPIC_MATCH_MAX_ATTEMPTS]:
        if _ask_topic_match(candidate.decision_text, candidate.reason or "명시되지 않음", statement):
            decision = candidate
            break

    if decision is None:
        return {"case": "none", "popup": None, "decision_id": None}

    decision_text = decision.decision_text
    decision_reason = decision.reason or "명시되지 않음"
    session_kwargs = {"session_meeting_id": session_meeting_id, "session_room_id": session_room_id}

    # 1단계: 새 값 제시 여부
    presents_new_value = _ask_judgment_step("presents_new_value", decision_text, decision_reason, statement)

    if not presents_new_value:
        # Case 0: 리마인더 - 세션당 1회
        return _decision_reminder_result(
            db, case="0", workspace_id=workspace_id, category_id=category_id,
            source_type=source_type, decision=decision, session_kwargs=session_kwargs,
        )

    # 2단계: 값이 같은가?
    same_as_existing = _ask_judgment_step("same_as_existing", decision_text, decision_reason, statement)

    if same_as_existing:
        # [수정 - 팀 결정] Case 1: 새 값을 제시하는 것처럼 말했지만 실제로는 기존
        # 결정과 같은 내용 - 이것도 "이미 결정된 이력이 있다"는 걸 알려주는 게
        # 사용자에게 유용하다고 판단, Case 0과 동일한 리마인더 팝업을 띄우도록 변경.
        # (예전엔 팝업 없이 조용히 무시했음)
        return _decision_reminder_result(
            db, case="1", workspace_id=workspace_id, category_id=category_id,
            source_type=source_type, decision=decision, session_kwargs=session_kwargs,
        )

    # 3단계: 근거가 명확한가?
    reason_is_clear = _ask_judgment_step("reason_is_clear", decision_text, decision_reason, statement)

    # Case 2/3: "모순"이 아니라 근거 명확성 기준의 "결정 변경"으로 구분한다.
    # 실제 decisions 반영은 여전히 post-meeting이 담당 - 여기선 알림 + 기록만 한다.
    if reason_is_clear:
        case, judgment_case = "2", "reasoned_change"
        message = (f"근거가 확인되어 결정이 바뀐 것으로 보입니다: '{statement}'"
                   f" (기존: {_format_decided_at(decision.decided_at)}에 결정된 '{decision.decision_text}')."
                   f" 바꾸시겠습니까?")
        # [수정 - 리뷰 반영] 새 발언의 근거를 별도 추출 - 기존 decision.reason(예전
        # 사유)이 아니라 "왜 지금 바뀌는지"를 보여줘야 함
        new_reason = _extract_change_reason(statement)
    else:
        case, judgment_case = "3", "unreasoned_change"
        message = (f"명확한 근거 없이 결정이 바뀐 것으로 보입니다: '{statement}'"
                   f" (기존: {_format_decided_at(decision.decided_at)}에 결정된 '{decision.decision_text}')."
                   f" 바꾸시겠습니까?")
        # [수정 - 라이브 테스트 발견] Case 3은 "근거가 명확하지 않음"이 핵심인데
        # 예전엔 여기에 decision.reason(기존 결정을 왜 그렇게 정했었는지)을 그대로
        # 넣고 있어서, "근거 없이 바뀜" 카드인데도 "이유"란에 뭔가 채워져서 나와
        # 모순돼 보였음. Case 3엔 애초에 보여줄 "지금 바뀐 이유"가 없으므로,
        # 고정 문구로 명확히 표시한다(프론트 변경 없이 안전하게 반영 가능).
        new_reason = "근거가 명확히 확인되지 않음"

    # [수정 - 라이브 테스트 발견] 예전엔 팝업 dedup을 (decision, judgment_case) 단위로
    # 걸어서, 같은 decision이라도 case가 다르면 각각 1회씩 떴다. 근데 실사용에서
    # STT가 하나의 연속된 발화를 두 세그먼트로 쪼개는 바람에, 앞부분만 보고 "근거
    # 불명확"(Case 3) 판단했다가 뒷부분까지 합쳐 다시 "근거 명확"(Case 2) 판단하면서
    # 같은 변경 하나에 모순되는 팝업 두 개가 동시에 뜨는 문제가 확인됨.
    #
    # "근거를 알게 됨"(Case 2)은 Case 3이 먼저 떴어도 항상 사용자에게 새로운
    # 정보지만, 그 반대(Case 2가 먼저 뜬 뒤 Case 3이 뜨는 것)는 이미 아는 것보다
    # 못한 정보라 보여줄 이유가 없다 - 그래서 dedup을 대칭이 아니라 "한쪽 방향으로만
    # 업그레이드 허용"으로 바꾼다. 세션 내 이 decision에 대해 Case 2가 이미 떴으면
    # 그 이후엔 Case 2/3 어느 쪽이 와도 더 보여줄 새 정보가 없으므로 무시하고,
    # Case 2가 아직 안 떴으면 Case 3은 (처음이든 반복이든) Case 3 자신의 기존
    # dedup만, Case 2는 항상 새 정보로 취급해 띄운다.
    already_shown_reasoned = contradiction_crud.already_popped_in_session_for_decision(
        db, reference_decision_id=decision.id, judgment_case="reasoned_change", **session_kwargs
    )
    if judgment_case == "unreasoned_change":
        already_shown_unreasoned = contradiction_crud.already_popped_in_session_for_decision(
            db, reference_decision_id=decision.id, judgment_case="unreasoned_change", **session_kwargs
        )
        already_popped = already_shown_reasoned or already_shown_unreasoned
    else:
        already_popped = already_shown_reasoned

    # make_deduplication_key의 3번째 인자명이 reference_file_id지만, decision 참조도
    # 같은 함수로 dedup key를 만들 수 있어 재사용 (해시 조합용이라 의미상 문제 없음)
    dedup_key = contradiction_crud.make_deduplication_key(
        source_type, source_id, decision.id, decision.id
    )
    # 팝업 노출 여부와 무관하게 매번 기록 - post-meeting이 세션 내 이 decision의
    # 최신 행을 그대로 사용자 확인 대상(변경 후보)으로 재사용한다.
    contradiction = contradiction_crud.create_contradiction(
        db,
        workspace_id=workspace_id, category_id=category_id,
        source_type=source_type, reference_type="decision",
        reference_decision_id=decision.id,
        statement_text_snapshot=statement,
        reference_text_snapshot=decision.decision_text,
        reason=new_reason,  # Case 2: 새 발언에서 추출한 변경 근거 / Case 3: 기존 결정의 사유(위 주석 참조)
        confidence_score=1.0,  # 벡터 점수 대신 topic_match가 이미 같은 주제로 확정한 것이라 고정값
        deduplication_key=dedup_key,
        judgment_case=judgment_case,
        **session_kwargs,
        **({"meeting_segment_id": source_id} if source_type == "meeting_segment"
           else {"room_message_id": source_id}),
    )

    if already_popped:
        return {"case": case, "popup": None, "decision_id": str(decision.id)}

    return {
        "case": case,
        "popup": {
            "type": judgment_case,
            "message": message,
            "contradiction_id": str(contradiction.id),
            "actions": ["change_acknowledged", "keep_reference"],
        },
        "decision_id": str(decision.id),
    }
