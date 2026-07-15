# backend/modules/llm/ollama_client.py
import os
import re
import sys
import json
import httpx
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")


# ── 유틸 ─────────────────────────────────────────────────────
def get_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def has_chinese(text: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', text))


# ── 시스템 프롬프트 ───────────────────────────────────────────
DOBY_SYSTEM_GUIDE = """
[언어 규칙 - 최우선 적용]
- 반드시 한국어로만 답변하라.
- 참고 내용이 영어로 되어있어도 답변은 반드시 한국어로 작성하라.
- 중국어, 일본어, 영어 등 한국어 외 언어 사용은 절대 금지한다.

너는 도비(Doby)라는 IT 프로젝트 업무 지원 AI 비서야.

[주요 역할]
- 업로드된 문서, PDF, 회의록, 개발 자료를 요약하고 설명한다.
- 문서 기반 질문에 답변한다.
- 회의록에서 담당자, 할 일, 마감일을 정리한다.
- 개인 일정이나 업무 일정을 정리하고 관리할 수 있도록 돕는다.
- 개발자, IT 직무 종사자, 프로젝트 팀원이 업무를 정리할 수 있도록 돕는다.

[제한 사항]
- 날씨, 뉴스, 주식, 실시간 검색처럼 현재 시스템에서 지원하지 않는 기능을 할 수 있다고 말하지 않는다.
- 지원하지 않는 기능을 물으면 불가능하다고만 끝내지 말고, 이 서비스에서 가능한 IT 문서/회의록/일정/업무 정리 기능을 안내한다.
- 참고 문서가 필요한 질문인데 참고 문서가 없으면 추측하지 않는다.
- 답변은 반드시 한국어로만 작성한다. 영어 문서를 참고해도 답변은 한국어로 번역해서 작성한다.
"""


# ── 기본 LLM 호출 함수들 ──────────────────────────────────────
def normalize_query(user_input: str) -> str:
    """은어/약어 → 표준어 변환"""
    if re.search(r'\.(pdf|docx|doc|md|txt|xlsx|pptx|csv)', user_input, re.IGNORECASE):
        return user_input

    prompt = f"[INST] [은어변환] {user_input} [/INST]"

    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=30.0
    )
    result = response.json()
    response_text = result.get("response", user_input).strip()

    try:
        parsed = json.loads(response_text)
        response_text = parsed.get("normalized", response_text)
    except:
        pass

    if has_chinese(response_text):
        print(f"[경고] 중국어 감지 → 원본 반환")
        return user_input

    return response_text


# ── 의도 분류 (4개 카테고리로 단순화) ──────────────────────────
VALID_INTENTS = [
    "task_from_rag",      # RAG 자료(회의록/문서) 기반 할일 추출
    "task_from_memory",   # 채팅 기록 기반 할일 추출
    "knowledge_search",   # RAG 자료로 답변 생성 (에러해결/문서질문/회의검색 등)
    "general_answer",     # RAG/memory 둘 다 불필요, 바로 답변
]

INTENT_CLASSIFICATION_PROMPT = """[INST] 다음 사용자 질문을 아래 4개 카테고리 중 정확히 하나로 분류하세요.

카테고리:
- task_from_rag: 회의록이나 업로드한 문서에서 할 일/액션아이템을 추출해달라는 요청.
  "그 문서", "이 파일", "업로드한 자료"처럼 특정 문서/파일을 가리키는 경우도 포함.
  예: "회의록에서 할 일 추출해줘", "그 문서에서 담당자별 업무 정리해줘",
      "이 파일에서 액션아이템 뽑아줘", "업로드한 회의록에서 할 일 정리해줘"

- task_from_memory: 방금 나눈 대화나 채팅 기록에서 할 일을 추출해달라는 요청
  예: "방금 대화에서 할 일 뽑아줘", "우리가 얘기한 내용에서 액션아이템 정리해줘"

- knowledge_search: 회의록/업로드문서/기술지식에서 정보를 찾아 답변이 필요한 질문.
  도커, 쿠버네티스, 깃허브, CI/CD, 배포, 네트워크 등 개발/인프라 기술 관련 질문도 포함.
  사용자가 업로드한 문서나 회의록이 없어도, 기술 관련 질문이면 이 카테고리로 분류.
  예: "저번 회의에서 뭐라고 했지", "쿠버 에러 어떻게 해결해", "도커 네트워크 종류 알려줘",
      "Dockerfile 멀티스테이지 빌드 방법", "배포 어떻게 해", "도커랑 쿠버 차이가 뭐야",
      "CI/CD 파이프라인 설정법", "그 문서 차트 제목이 뭐였지", "이거 요약해줘"

- general_answer: 개발/인프라 기술과 무관한 일반 질문, 인사, 용어 설명
  예: "winmain이 뭐야", "안녕", "고마워", "오늘 날씨 어때", "파이썬이 뭐야"

반드시 아래 JSON 형식으로만 답하세요. 다른 설명은 절대 쓰지 마세요.
{{"intent": "카테고리명"}}

질문: {user_input} [/INST]"""


def classify_intent(user_input: str) -> dict:
    """사용자 질문 의도 파악 (개 카테고리)"""
    prompt = INTENT_CLASSIFICATION_PROMPT.format(user_input=user_input)

    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=30.0
    )
    result = response.json()
    response_text = result.get("response", "general_answer").strip()

    try:
        parsed = json.loads(response_text)
        intent = parsed.get("intent", "general_answer").strip().lower()
    except:
        intent = response_text.strip().lower()

    if intent not in VALID_INTENTS:
        print(f"[classify_intent] 알 수 없는 intent: '{intent}' → general_answer로 대체")
        intent = "general_answer"

    return {"intent": intent, "original_input": user_input}


def generate_answer(user_input: str, context: str = "") -> str:
    """기본 LLM 호출 — 프롬프트 직접 넘길 때 사용"""
    if context:
        prompt = f"""[INST] 당신은 한국어 개발자 AI 비서입니다.
반드시 한국어로만 답하세요. 중국어 사용 절대 금지.
아래 참고 문서를 바탕으로 질문에 답하세요.
인사말 없이 핵심만 답하세요.

참고 문서:
{context}

질문: {user_input} [/INST]"""
    else:
        prompt = f"""[INST] 당신은 한국어 개발자 AI 비서입니다.
반드시 한국어로만 답하세요. 중국어 사용 절대 금지.
질문에 핵심만 간결하게 답하세요.

질문: {user_input} [/INST]"""

    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=60.0
    )
    result = response.json()
    response_text = result.get("response", "답변 생성 실패").strip()

    if has_chinese(response_text):
        print(f"[경고] 중국어 감지 → 재시도")
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt + "\n한국어로만 답하세요.", "stream": False},
            timeout=60.0
        )
        result = response.json()
        response_text = result.get("response", "답변 생성 실패").strip()

    return response_text


# ── 내부 유틸 ────────────────────────────────────────────────

def _format_low_confidence_notice(retrieved_docs: list) -> str:
    """
    low_confidence=True일 때 사용자에게 보여줄 안내 문구.
    retrieved_docs: rag_service의 data 리스트 (title, score 키 포함).
    """
    if not retrieved_docs:
        return "관련 문서를 찾을 수 없습니다."

    lines = [f"관련 문서를 찾을 수 없습니다. 낮은 유사도로 검색된 문서 {len(retrieved_docs)}개:"]
    for doc in retrieved_docs:
        title = doc.get("title", "제목 없음")
        score = doc.get("score", 0)
        lines.append(f"- {title} (유사도 {score:.4f})")
    return "\n".join(lines)


def _build_context_from_docs(docs: list, max_chars: int = 6000) -> str:
    """문서 리스트를 LLM에 넘길 컨텍스트 문자열로 변환."""
    parts = []
    for doc in docs:
        title = doc.get("title", "제목 없음")
        content = doc.get("content", "")
        parts.append(f"[{title}]\n{content}")
    return "\n\n".join(parts)[:max_chars]


def _call_ollama(prompt: str, timeout: float = 150.0) -> str:
    """Ollama 단일 호출 + 중국어 감지 재시도 (최대 3회)."""
    # 프롬프트 끝에 한국어 강제 지시 추가
    ko_suffix = "\n\n[중요] 반드시 한국어로만 답하세요. 중국어 사용 절대 금지."

    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt + ko_suffix, "stream": False},
        timeout=timeout,
    )
    text = response.json().get("response", "답변 생성 실패").strip()

    # 중국어 감지 시 최대 2회 추가 재시도
    for attempt in range(2):
        if not has_chinese(text):
            break
        print(f"[경고] 중국어 감지 → 재시도 {attempt + 1}/2")
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt + ko_suffix + "\n한국어 외 다른 언어는 절대 사용하지 마세요.",
                "stream": False,
            },
            timeout=timeout,
        )
        text = response.json().get("response", "답변 생성 실패").strip()

    if has_chinese(text):
        print("[경고] 3회 재시도 후에도 중국어 감지됨 — 그대로 반환")

    return text


def _answer_knowledge_search(
    user_message: str,
    rag_search_result: dict,
) -> str:
    """
    knowledge_search 타입 + rag_search_result(컬렉션별 분리 결과)가 있을 때
    4가지 경우로 분기해서 프롬프트를 구성하고 LLM을 호출한다.

    [분기 기준]
    - meeting 찾음: collection_results["meeting"]["count"] > 0
                    AND NOT collection_results["meeting"]["low_confidence"]
    - knowledge 찾음: collection_results["knowledge"]["count"] > 0
                      AND NOT collection_results["knowledge"]["low_confidence"]

    [분기 1] meeting O + knowledge O
    → 회의록 내용 기반으로 답변, 지식 문서로 보충

    [분기 2] meeting O + knowledge X
    → 회의록 내용만으로 답변

    [분기 3] meeting X + knowledge O
    → "회의록은 찾지 못했습니다" 안내 후 지식 문서로 설명

    [분기 4] meeting X + knowledge X
    → "관련 내용을 찾지 못했습니다" 안내 + 가능하면 일반 지식으로 보충
    """
    cr = rag_search_result.get("collection_results", {})
    searched = rag_search_result.get("searched_collections", [])

    meeting_cr   = cr.get("meeting",   {"count": 0, "low_confidence": True, "data": []})
    document_cr  = cr.get("document",  {"count": 0, "low_confidence": True, "data": []})
    knowledge_cr = cr.get("knowledge", {"count": 0, "low_confidence": True, "data": []})

    meeting_found        = meeting_cr["count"]   > 0 and not meeting_cr["low_confidence"]
    document_found       = document_cr["count"]  > 0 and not document_cr["low_confidence"]
    knowledge_found      = knowledge_cr["count"] > 0 and not knowledge_cr["low_confidence"]
    # 실제로 meeting_collection을 검색 대상으로 선택했는지 여부
    # → 회의 관련 신호어가 있는 질문에서만 True
    meeting_was_searched = "meeting" in searched

    meeting_context   = _build_context_from_docs(meeting_cr.get("data", []))
    document_context  = _build_context_from_docs(document_cr.get("data", []))
    knowledge_context = _build_context_from_docs(knowledge_cr.get("data", []))

    # ── 분기 0: 업로드 문서 찾음 ────────────────────────────────
    # document_collection은 사용자가 직접 업로드한 문서
    # knowledge/meeting보다 우선순위 높음 (사용자가 특정 문서를 가리킨 경우)
    if document_found and not meeting_found and not knowledge_found:
        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

아래 [참고 문서]는 사용자가 업로드한 문서입니다.
[참고 문서]이 비어 있지 않다면 절대 "참고 문서가 없다"고 말하지 마세요.

[참고 문서]
{document_context}

[사용자 질문]
{user_message}

[답변 규칙]
- 반드시 [참고 문서]만 근거로 답하세요.
- 참고 문서에 없는 정보는 추측하지 마세요.
- 사용자가 요약을 요청하면 핵심 내용을 한국어로 정리하세요.
- 인사말(안녕하세요 등)로 시작하지 마세요.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마세요.
- 코드가 포함된 답변이면 반드시 코드 블록(```언어명 ... ```)으로 감싸세요.
- 인사말 없이 바로 핵심 내용부터 답변하세요.
- 답변은 한국어로 작성하세요.
[/INST]"""
        return _call_ollama(prompt)

    # document + knowledge 둘 다 찾음
    if document_found and knowledge_found and not meeting_found:
        combined_context = document_context + "\n\n" + knowledge_context
        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

아래 [참고 내용]은 사용자가 업로드한 문서와 관련 기술 문서입니다.
[참고 내용]이 비어 있지 않다면 절대 "참고 문서가 없다"고 말하지 마세요.

[참고 내용]
{combined_context}

[사용자 질문]
{user_message}

[답변 규칙]
- 반드시 [참고 내용]만 근거로 답하세요.
- 참고 내용에 없는 정보는 추측하지 마세요.
- 인사말(안녕하세요 등)로 시작하지 마세요.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마세요.
- 코드가 포함된 답변이면 반드시 코드 블록(```언어명 ... ```)으로 감싸세요.
- 인사말 없이 바로 핵심 내용부터 답변하세요.
- 답변은 한국어로 작성하세요.
[/INST]"""
        return _call_ollama(prompt)

    # ── 분기 1: 둘 다 찾음 ───────────────────────────────────
    if meeting_found and knowledge_found:
        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

[회의록 내용]
{meeting_context}

[관련 기술 문서]
{knowledge_context}

[사용자 질문]
{user_message}

[답변 규칙]
- 먼저 회의록에서 찾은 관련 내용을 요약해서 답하세요.
- 그 다음, 관련 기술 문서를 바탕으로 구체적인 해결 방법이나 추가 설명을 이어서 제공하세요.
- 각 출처(회의록 / 기술 문서)를 구분해서 명확히 표시하세요.
- 인사말(안녕하세요 등)로 시작하지 마세요.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마세요.
- 코드가 포함된 답변이면 반드시 코드 블록(```언어명 ... ```)으로 감싸세요.
- 인사말 없이 바로 핵심 내용부터 답변하세요.
- 답변은 한국어로 작성하세요.
[/INST]"""
        return _call_ollama(prompt)

    # ── 분기 2: 회의록만 찾음 ────────────────────────────────
    if meeting_found and not knowledge_found:
        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

[회의록 내용]
{meeting_context}

[사용자 질문]
{user_message}

[답변 규칙]
- 회의록 내용만을 근거로 답하세요.
- 회의록에 없는 내용은 추측하지 마세요.
- 인사말(안녕하세요 등)로 시작하지 마세요.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마세요.
- 코드가 포함된 답변이면 반드시 코드 블록(```언어명 ... ```)으로 감싸세요.
- 인사말 없이 바로 핵심 내용부터 답변하세요.
- 답변은 한국어로 작성하세요.
[/INST]"""
        return _call_ollama(prompt)

    # ── 분기 3a: 순수 기술 질문 (meeting 검색 안 함 + knowledge 찾음) ─
    # meeting_was_searched=False면 처음부터 회의 의도가 없는 질문이므로
    # 회의록 언급 없이 바로 기술 문서 기반으로 답변
    if not meeting_was_searched and knowledge_found:
        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

아래 [참고 내용]은 사용자 질문과 관련된 기술 문서입니다.
[참고 내용]이 비어 있지 않다면 절대 "참고 문서가 없다"고 말하지 마세요.

[참고 내용]
{knowledge_context}

[사용자 질문]
{user_message}

[답변 규칙]
- 반드시 [참고 내용]만 근거로 답하세요.
- 참고 내용에 없는 정보는 추측하지 마세요.
- 사용자가 요약을 요청하면 핵심 내용을 한국어로 정리하세요.
- 인사말(안녕하세요 등)로 시작하지 마세요.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마세요.
- 코드가 포함된 답변이면 반드시 코드 블록(```언어명 ... ```)으로 감싸세요.
- 인사말 없이 바로 핵심 내용부터 답변하세요.
- 답변은 한국어로 작성하세요.
[/INST]"""
        return _call_ollama(prompt)

    # ── 분기 3b: 회의록 검색 시도했지만 못 찾음 + knowledge 찾음 ──
    if not meeting_found and knowledge_found and meeting_was_searched:
        meeting_notice = ""
        if meeting_cr["count"] > 0:
            # 회의록을 검색했지만 유사도가 낮아 못 찾은 경우 → 목록 안내
            titles = [d.get("title", "제목 없음") for d in meeting_cr.get("data", [])[:3]]
            meeting_notice = f"관련 회의록을 찾지 못했습니다. (낮은 유사도로 검색된 회의록: {', '.join(titles)})"
        else:
            # 회의록 컬렉션 자체에 데이터가 없는 경우
            meeting_notice = "등록된 회의록이 없습니다."

        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

[관련 기술 문서]
{knowledge_context}

[사용자 질문]
{user_message}

[답변 규칙]
- 먼저 "{meeting_notice}"라고 자연스럽게 안내하세요.
- 그 다음, 관련 기술 문서를 바탕으로 질문에 답하세요.
- 기술 문서에 없는 내용은 추측하지 마세요.
- 인사말(안녕하세요 등)로 시작하지 마세요.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마세요.
- 코드가 포함된 답변이면 반드시 코드 블록(```언어명 ... ```)으로 감싸세요.
- 인사말 없이 바로 핵심 내용부터 답변하세요.
- 답변은 한국어로 작성하세요.
[/INST]"""
        return _call_ollama(prompt)

    # ── 분기 4: 둘 다 못 찾음 (또는 meeting 검색 안 한 케이스) ──
    # 도비는 크롤링/업로드된 문서 기반 AI 비서이므로,
    # 관련 문서를 찾지 못한 경우 일반 지식으로 추측해서 답하지 않음.
    # 키워드 보강 또는 파인튜닝으로 검색 정확도를 올리는 방향으로 개선 예정.
    all_docs = rag_search_result.get("data", [])

    if meeting_was_searched and all_docs:
        # 회의록 검색 시도했지만 둘 다 낮은 신뢰도 → 회의록 관련 안내 포함
        doc_list = "\n".join(
            f"- {d.get('title', '제목 없음')} (유사도 {d.get('score', 0):.4f})"
            for d in all_docs[:5]
        )
        return (
            f"관련 회의록과 기술 문서 모두에서 충분한 정보를 찾지 못했습니다.\n"
            f"낮은 유사도로 검색된 문서 {len(all_docs[:5])}개:\n{doc_list}\n\n"
            f"관련 문서가 등록되어 있는지 확인하거나, 질문을 더 구체적으로 입력해 주세요."
        )
    elif all_docs:
        # 순수 기술 질문인데 신뢰도 낮음 → 기술 문서 관련 안내
        doc_list = "\n".join(
            f"- {d.get('title', '제목 없음')} (유사도 {d.get('score', 0):.4f})"
            for d in all_docs[:5]
        )
        return (
            f"관련 기술 문서에서 충분한 정보를 찾지 못했습니다.\n"
            f"낮은 유사도로 검색된 문서 {len(all_docs[:5])}개:\n{doc_list}\n\n"
            f"관련 문서가 등록되어 있는지 확인하거나, 질문을 더 구체적으로 입력해 주세요."
        )
    else:
        return "관련 문서를 찾지 못했습니다. 질문을 더 구체적으로 입력하거나 관련 문서를 먼저 업로드해 주세요."


# ── 흐름별 답변 생성 ──────────────────────────────────────────
def generate_answer_for_graph(
    user_message: str,
    question_type: str = "general_answer",
    rag_context: str = "",
    memory_context: str = "",
    tasks: list = None,
    low_confidence: bool = False,
    retrieved_docs: list = None,
    rag_search_result: dict = None,
) -> str:
    """
    question_type에 따라 프롬프트 자동 구성 후 LLM 호출.
    question_type 4개: task_from_rag, task_from_memory,
                        knowledge_search, general_answer

    [수정 사항 - 2026.06.17]
    knowledge_search 분기에서 발생하던 "참고 문서가 제공되지 않았습니다" 오답 수정.
    원인: 이 함수 안에서 만든 prompt(시스템가이드+규칙+질문 전체)를
          generate_answer(prompt, context=rag_context)로 다시 감싸서 호출하면,
          generate_answer 내부 템플릿의 "질문:" 자리에 그 prompt 전체가
          통째로 들어가 버려 이중 래핑이 발생했음. STT 전사처럼 rag_context가
          길 때 이 구조 때문에 모델이 참고 문서 위치를 못 찾는 경우가 있었음.
    수정: knowledge_search 분기는 generate_answer()를 거치지 않고
          Ollama를 직접 호출하도록 변경. rag_context가 비어있으면 LLM 호출 전에
          바로 안내 문구를 반환하고, 비어있지 않으면 "참고 문서가 없다고
          말하지 말라"는 지시를 프롬프트에 명시함.

          참고: question_type 표기 차이(예: task_from_RAG vs task_from_rag)는
          여기서 방어하지 않음. VALID_INTENTS와 classify_intent()가 이미
          소문자(task_from_rag)로 일관되게 정의되어 있으므로, 대문자로 들어오는
          입력은 호출하는 쪽(graph 노드 등)의 문제임. 해당 쪽에서 수정 필요.

    [수정 사항 - 2026.06.18]
    low_confidence / retrieved_docs 파라미터 추가.
    rag_service.retrieve_relevant_knowledge()가 검색 결과의 최고 점수가
    LOW_CONFIDENCE_THRESHOLD(0.3) 미만이면 low_confidence=True를 반환하도록
    바뀌었음. 이 경우 적재 단계에서는 문서를 탈락시키지 않지만(크롤링 철학),
    답변 단계에서는 "관련 문서를 찾을 수 없습니다"라고 먼저 안내하고,
    그 다음 질문이 일반 기술 지식으로 답변 가능하면 그 설명을 이어서
    제공하도록 프롬프트를 구성함. retrieved_docs는 낮은 유사도로 검색된
    문서명+점수를 사용자에게 참고용으로 보여주기 위해 사용함.
    """
    tasks = tasks or []
    rag_context = rag_context or ""
    memory_context = memory_context or ""
    retrieved_docs = retrieved_docs or []

    # ── knowledge_search ─────────────────────────────────────
    if question_type == "knowledge_search":
        if rag_search_result:
            cr = rag_search_result.get("collection_results", {})
            has_results = any(
                cr.get(key, {}).get("count", 0) > 0
                for key in ["meeting", "document", "knowledge"]
            )
            if has_results:
                return _answer_knowledge_search(user_message, rag_search_result)
            # collection_results 비어있음 → rag_context 기반으로 fallback

        # 유형 1: target_document_id로 문서를 직접 조회한 경우 (기존 로직 유지)
        # rag_context는 SQLite documents 테이블의 content_markdown 전체
        if not rag_context.strip():
            return "참고할 문서 내용을 찾지 못했습니다. 문서가 정상적으로 업로드되었는지 확인해 주세요."

        trimmed_context = rag_context[:12000]
        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

아래 [참고 내용]은 사용자가 선택한 문서 또는 음성 전사 내용입니다.
[참고 내용]이 비어 있지 않다면 절대 "참고 문서가 없다"고 말하지 마세요.

[참고 내용]
{trimmed_context}

[사용자 질문]
{user_message}

[답변 규칙]
- 반드시 [참고 내용]만 근거로 답하세요.
- 참고 내용에 없는 정보는 추측하지 마세요.
- 사용자가 요약을 요청하면 핵심 내용을 한국어로 정리하세요.
- 인사말(안녕하세요 등)로 시작하지 마세요.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마세요.
- 코드가 포함된 답변이면 반드시 코드 블록(```언어명 ... ```)으로 감싸세요.
- 인사말 없이 바로 핵심 내용부터 답변하세요.
- 답변은 한국어로 작성하세요.
[/INST]"""
        return _call_ollama(prompt)

    # ── task_from_rag / task_from_memory ──
    if question_type in ("task_from_rag", "task_from_memory") and tasks:
        task_context = json.dumps(tasks, ensure_ascii=False, indent=2)
        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

아래 추출된 할 일 목록을 보기 좋게 정리해줘.

[규칙]
- 담당자, 할 일, 마감일이 있으면 구분해서 정리해라.
- 없는 정보는 임의로 만들지 마라.
- 마감일 형식은 가능한 한 통일해서 보여줘라.
- 인사말(안녕하세요 등)로 시작하지 마라.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마라.
- 인사말 없이 바로 핵심 내용부터 답변해라.
- 답변은 한국어로 작성해라.

사용자 질문:
{user_message}

할 일 목록:
{task_context}
[/INST]"""
        return _call_ollama(prompt)

    # ── summary_from_rag ──
    if question_type == "summary_from_rag" and rag_context:
        trimmed_context = rag_context[:12000]
        prompt = f"""[INST]
{DOBY_SYSTEM_GUIDE}

아래 [참고 문서]는 사용자가 업로드한 문서 또는 회의록입니다.
[참고 문서]이 비어 있지 않다면 절대 "참고 문서가 없다"고 말하지 마세요.

[참고 문서]
{trimmed_context}

[사용자 질문]
{user_message}

[답변 규칙]
- 반드시 [참고 문서]만 근거로 요약하세요.
- 참고 문서에 없는 내용은 추가하지 마세요.
- 핵심 주제, 주요 결론, 중요 수치나 이름 위주로 정리하세요.
- 인사말(안녕하세요 등)로 시작하지 마세요.
- 마무리 문구(도움이 되셨으면 합니다 등)로 끝내지 마세요.
- 인사말 없이 바로 핵심 내용부터 답변하세요.
- 답변은 한국어로 작성하세요.
[/INST]"""
        return _call_ollama(prompt)

    # ── general_answer 또는 fallback ──
    prompt = f"""
{DOBY_SYSTEM_GUIDE}

사용자 질문에 답해줘.

[규칙]
- 도비가 할 수 있는 일은 IT 프로젝트 업무 지원, 문서 요약, 회의록 정리, 문서 기반 질의응답, 할 일 추출이다.
- 날씨, 뉴스, 주식, 실시간 검색 같은 기능을 할 수 있다고 말하지 마라.
- 답변은 한국어로 작성해라.

사용자 질문:
{user_message}
"""
    return generate_answer(prompt)


# ── 할 일 추출 ────────────────────────────────────────────────
def extract_tasks_from_content(content: str) -> list[dict]:
    """회의록/문서/채팅기록에서 담당자별 할 일 추출"""
    if not content or not content.strip():
        return []

    prompt = f"""[INST]
아래 내용에서 담당자별 할 일을 JSON 배열로만 추출해줘.

[규칙]
- 반드시 JSON 배열만 반환해라.
- 각 항목은 task_id, task, assignee, deadline, status 필드를 가져야 한다.
- task_id는 "0001", "0002" 형식으로 생성해라.
- 담당자나 마감일이 없으면 null로 둔다.
- status 기본값은 "todo"로 둔다.
- 원문에 없는 내용은 만들지 마라.
- 설명 문장은 쓰지 마라.
- 회의록뿐 아니라 대화 기록, 채팅 내용에서도 할 일을 추출해라.
- "~해야 해", "~하기로 했어", "~할게", "~맡을게" 같은 표현도 할 일로 인식해라.
- 사용자의 질문 자체("~가 뭐야?", "~해줘", "~추출해줘" 등)는 할 일로 추출하지 마라.
- 실제 업무, 담당자, 마감일이 언급된 경우에만 할 일로 추출해라.
- 추출할 할 일이 없으면 빈 배열 []을 반환해라.

[마감일 규칙]
- 원문에 연도가 있으면 "YYYY년 M월 D일" 형식으로 작성해라.
- 원문에 연도가 없고 월/일만 있으면 원문 표현 그대로 사용해라.
- "다음 주", "금요일", "내일", "이번 주" 같은 상대적 표현은 그대로 반환해라.
- 절대로 연도나 월을 임의로 추가하거나 변환하지 마라.
- 마감일을 알 수 없으면 null로 둔다.

원본 내용:
{content}

JSON:
[/INST]"""

    raw_answer = _call_ollama(prompt)
    return _parse_json_array(raw_answer)


# ── 화자분리 보완 ─────────────────────────────────────────────
def enhance_diarization(segments: list[dict]) -> list[dict]:
    """
    STT 화자분리 결과 보완.
    문맥 기반으로 잘못 분리된 발화 수정, speaker 레이블은 유지.
    중국어 감지 or JSON 파싱 실패 시 원본 segments 그대로 반환.
    """
    transcript = "\n".join(
        f"[{s.get('speaker', 'UNKNOWN')} {s.get('start', 0):.1f}s] {s.get('text', '')}"
        for s in segments
    )

    prompt = f"""[INST] [화자분리보완]
아래는 자동 화자분리된 STT 결과입니다.
문맥을 보고 잘못 분리된 발화만 수정하세요.
speaker 레이블(SPEAKER_00 등)은 변경하지 말고 그대로 유지하세요.
반드시 아래 JSON 배열 형식으로만 출력하세요. 다른 말 하지 마세요.
중국어 사용 절대 금지.

입력:
{transcript}

출력 형식:
[
  {{"speaker": "SPEAKER_00", "start": 0.0, "end": 3.2, "text": "발화 내용"}},
  ...
] [/INST]"""

    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60.0
        )
        response_text = response.json().get("response", "").strip()

        if has_chinese(response_text):
            print(f"[경고] 화자분리 중국어 감지 → 원본 반환")
            return segments

        json_match = response_text[response_text.find("["):response_text.rfind("]") + 1]
        enhanced = json.loads(json_match)

        if not enhanced:
            return segments

        print(f"[ollama_client] 화자분리 보완 완료: {len(enhanced)}개 발화")
        return enhanced

    except Exception as e:
        print(f"[ollama_client] 화자분리 보완 실패, 원본 사용: {e}")
        return segments


# ── 내부 유틸 ─────────────────────────────────────────────────
def _parse_json_array(text: str) -> list[dict]:
    """LLM 응답에서 JSON 배열만 추출"""
    if not text:
        return []

    cleaned = re.sub(r"```json", "", text.strip())
    cleaned = re.sub(r"```", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "tasks" in parsed:
            return parsed["tasks"]
        return []
    except:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, list) else []
        except:
            return []

# ── 음성 회의록 분석 함수들 ───────────────────────────────────

def generate_voice_summary(content: str) -> str | None:
    """음성 전사 내용 요약 (한두 문단)"""
    if not content or not content.strip():
        return None

    prompt = f"""[INST]
아래는 음성 회의록의 전사 내용입니다. 전체 내용을 한두 문단으로 요약해줘.

[규칙]
- 회의의 주요 주제와 결론을 중심으로 요약해라.
- 원본에 없는 내용은 추가하지 마라.
- 한국어로 작성해라.
- 제목은 만들지 마라.
- 2~3문단 이내로 작성해라.

전사 내용:
{content[:8000]}

요약:
[/INST]"""
    return _call_ollama(prompt)


def extract_keywords_with_count(content: str) -> list[dict]:
    """
    음성/문서 내용에서 핵심 키워드와 빈도수 추출.
    반환: [{"word": "마케팅", "count": 24}, ...]
    """
    if not content or not content.strip():
        return []

    # 빈도수는 LLM 추출 후 실제 텍스트에서 카운트
    prompt = f"""[INST]
아래 내용에서 핵심 키워드 10~15개를 추출해줘.
반드시 JSON 배열로만 반환해라. 다른 설명은 쓰지 마라.

[규칙]
- 조사, 접속사, 대명사 등 의미 없는 단어는 제외해라.
- 기술 용어, 프로젝트명, 담당자명, 주요 업무 키워드 위주로 추출해라.
- 반드시 아래 형식의 JSON 배열만 반환해라.

출력 형식:
["키워드1", "키워드2", "키워드3"]

내용:
{content[:6000]}

JSON:
[/INST]"""

    raw = _call_ollama(prompt)

    # JSON 파싱
    try:
        cleaned = re.sub(r"```json|```", "", raw.strip()).strip()
        keywords = json.loads(cleaned)
        if not isinstance(keywords, list):
            return []
    except Exception:
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not match:
            return []
        try:
            keywords = json.loads(match.group(0))
        except Exception:
            return []

    # 실제 텍스트에서 빈도수 카운트
    result = []
    content_lower = content.lower()
    for kw in keywords:
        if not isinstance(kw, str) or not kw.strip():
            continue
        count = content_lower.count(kw.lower())
        if count > 0:
            result.append({"word": kw.strip(), "count": count})

    # 빈도수 내림차순 정렬
    result.sort(key=lambda x: x["count"], reverse=True)
    return result


def extract_timestamps(transcription: list[dict]) -> list[dict]:
    """
    STT transcription에서 주요 발화 타임스탬프 추출.
    transcription: [{"speaker": "SPEAKER_00", "start": 0.0, "end": 3.2, "text": "..."}]
    반환: [{"time": "00:14:30", "summary": "신규 채널 전략 논의"}, ...]
    """
    if not transcription:
        return []

    # 전사 내용을 텍스트로 변환
    transcript_text = "\n".join(
        f"[{int(s.get('start', 0) // 60):02d}:{int(s.get('start', 0) % 60):02d}] "
        f"{s.get('speaker', 'SPEAKER')}: {s.get('text', '')}"
        for s in transcription
    )

    prompt = f"""[INST]
아래는 음성 회의록의 타임스탬프별 전사 내용입니다.
중요한 발화 10개 이내를 골라서 각 시간대의 핵심 내용을 한 줄로 요약해줘.
반드시 JSON 배열로만 반환해라. 다른 설명은 쓰지 마라.

출력 형식:
[
  {{"time": "00:00", "summary": "회의 시작 및 안건 소개"}},
  {{"time": "05:30", "summary": "신규 기능 개발 방향 논의"}}
]

전사 내용:
{transcript_text[:6000]}

JSON:
[/INST]"""

    raw = _call_ollama(prompt)

    try:
        cleaned = re.sub(r"```json|```", "", raw.strip()).strip()
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except Exception:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, list):
                    return result
            except Exception:
                pass
    return []

# ── 테스트 ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== 은어 변환 테스트 ===")
    result = normalize_query("쿠버 파드 뻗었어")
    print(f"변환 결과: {result}")

    print("\n=== 의도 분류 테스트 (4개 카테고리) ===")
    test_queries = [
        "회의록에서 할 일 추출해줘",
        "방금 대화에서 할 일 뽑아줘",
        "쿠버 파드 뻗었는데 어떻게 해결해",
        "이 문서 요약해줘",
        "winmain이 뭐야",
    ]
    for q in test_queries:
        result = classify_intent(q)
        print(f"'{q}' → {result['intent']}")