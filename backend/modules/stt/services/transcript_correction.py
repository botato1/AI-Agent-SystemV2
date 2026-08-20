"""
전사된 회의록을 LLM이 **문맥으로 읽고** 오인식을 고친다.

왜 용어 목록으로는 부족한가:
  지금까지는 틀린 단어를 발견할 때마다 terms_context.txt에 손으로 추가했다.
  그건 이해가 아니라 암기다 — 다음 회의에서 목록에 없는 단어가 나오면 똑같이 틀리고,
  사람이 또 목록에 추가해야 한다. 회의 주제가 바뀌면 목록 전체가 낡는다.

  사람은 목록 없이도 고친다. "그럼 이전 결정 **반복**하고 재논의 상태 기능도"를 읽으면
  결정을 되풀이한다는 말이 문맥에 안 맞으니 **번복**이라고 유추한다. 문장의 뜻으로
  아는 것이지 단어를 외워서가 아니다. LLM에게 시킬 수 있는 일이 정확히 이것이다.

  (실제로 그 "번복→반복"은 뜻이 정반대로 뒤집혀 모순 감지에 직접 타격을 줬다.
   결정을 뒤집었다는 문장이 되풀이했다는 문장이 되기 때문이다.)

왜 재분석 경로에 두는가:
  백그라운드라 지연 제약이 없다. 실시간 자막에 LLM을 물리면 응답성이 무너진다.
  회의록은 사용자가 나중에 열어보는 최종본이라 몇 초 더 걸려도 된다.

⚠️ 가장 큰 위험은 **멀쩡한 문장을 LLM이 고쳐버리는 것**이다. 전사가 조금 틀린 것보다
   내용이 바뀌는 쪽이 훨씬 나쁘다(모순 감지가 없던 모순을 만들어낼 수 있다).
   그래서 모델을 믿지 않고 코드로 막는다:
     - 글자 변경 비율이 한도를 넘으면 거부 (문장 재작성 차단)
     - 길이가 크게 달라지면 거부 (내용 추가/삭제 차단)
     - 빈 문자열 거부
     - 원문은 항상 text_original에 보존 — 되돌릴 수 있어야 한다
   LLM이 못 미덥게 굴어도 최악의 경우 "아무것도 안 고침"으로 끝나야 한다.

실패해도 재분석 전체를 망가뜨리지 않는다 — LLM이 없거나 죽어 있으면 원문 그대로 둔다.
"""
import json
import re
import urllib.error
import urllib.request

from ..core.config import (
    logger,
    REFINE_LLM_ENABLED,
    REFINE_LLM_BACKEND,
    REFINE_LLM_LOCAL_MODEL,
    REFINE_LLM_URL,
    REFINE_LLM_MODEL,
    REFINE_LLM_TIMEOUT,
    REFINE_LLM_BATCH,
    REFINE_LLM_CONTEXT_LINES,
    REFINE_LLM_MAX_EDIT_RATIO,
)

_SYSTEM = """너는 한국어 회의록 교정기다. 음성 인식이 잘못 알아들은 단어만 고친다.

규칙:
1. 발음이 비슷해서 잘못 인식된 단어만 고친다. 예: "이전 결정 반복하고" → "이전 결정 번복하고"
2. 문맥상 명백히 틀린 것만 고친다. 조금이라도 확신이 없으면 그대로 둔다.
3. 문장을 다시 쓰지 마라. 말투, 어순, 문장 구조를 바꾸지 마라.
4. 내용을 요약하거나 다듬지 마라. 말을 더듬은 부분, 반복, 어색한 표현은 그대로 둔다.
5. 없는 내용을 추가하지 마라.
6. 고칠 게 없으면 빈 배열을 반환한다.

출력은 JSON 배열만. 설명 금지.
[{"i": 줄번호, "text": "고친 문장 전체"}]"""


def _edit_ratio(before: str, after: str) -> float:
    """
    글자 단위 변경 비율(0~1) — 실제 편집거리로 잰다.

    처음엔 공통 접두/접미만 잘라내는 방식으로 대충 셌는데, **앞부분이 바뀌면 뒤가
    다 같아도 전부 '바뀐 것'으로 세는** 결함이 있었다. 실측에서 두 곳만 고친 교정
    ("범위하면 범위는 ... 동마크" → "범위는 ... 북마크")이 96%로 계산돼 거부됐다.

    이 값이 곧 "문장을 다시 썼는가"의 판정 기준이므로, 부정확하면 멀쩡한 교정을
    막거나(위 사례) 반대로 재작성을 통과시킨다. 정확하게 재는 편이 맞다.
    """
    if not before:
        return 1.0
    previous = list(range(len(after) + 1))
    for i, b in enumerate(before, 1):
        current = [i]
        for j, a in enumerate(after, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (b != a)))
        previous = current
    return previous[-1] / len(before)


def _parse_corrections(raw: str) -> list[dict]:
    """LLM 출력에서 JSON 배열을 건져낸다. 코드펜스나 잡담이 섞여 나와도 견딘다."""
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    match = re.search(r"\[.*\]", text, flags=re.S)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


_local_pipe = None
_local_failed = False


def _ask_local(prompt: str) -> str | None:
    """
    같은 서버에 받아둔 모델을 직접 돌린다.

    왜 이 경로가 있나: Ollama는 다른 팀원이 띄운 서버라 주소를 받아야 하고, 우리
    재분석이 그쪽에 부하를 준다. 서버에 이미 받아둔 모델이 있으면 남에게 기대지 않고
    끝낼 수 있다. 다만 GPU 메모리를 STT 모델과 나눠 쓰므로 4bit 모델을 기본으로 둔다.

    재분석은 백그라운드이고 락으로 직렬화돼 한 번에 하나만 도므로, 여기서 잠깐
    메모리를 더 쓰는 것은 실시간 자막에 영향을 주지 않는다.
    """
    global _local_pipe, _local_failed
    if _local_failed:
        return None
    if _local_pipe is None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            logger.info(f"🧠 교정용 LLM 로딩 중... ({REFINE_LLM_LOCAL_MODEL})")
            tokenizer = AutoTokenizer.from_pretrained(REFINE_LLM_LOCAL_MODEL)
            model = AutoModelForCausalLM.from_pretrained(
                REFINE_LLM_LOCAL_MODEL, dtype="auto", device_map="auto",
            )
            _local_pipe = (tokenizer, model)
            logger.info("✅ 교정용 LLM 로딩 완료")
        except Exception as e:
            _local_failed = True
            logger.warning(f"⚠️ 교정용 LLM을 못 씀 — 원문 유지: {e}")
            return None

    tokenizer, model = _local_pipe
    try:
        import torch
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ]
        inputs = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt", return_dict=True,
        ).to(model.device)
        with torch.no_grad():
            # 교정은 창의성이 필요 없다. 샘플링을 켜면 멀쩡한 문장을 건드린다.
            out = model.generate(**inputs, max_new_tokens=1024, do_sample=False)
        return tokenizer.decode(out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
    except Exception:
        logger.exception("⚠️ 교정용 LLM 추론 실패 — 원문 유지")
        return None


def _ask_ollama(prompt: str) -> str | None:
    """Ollama /api/chat 호출. 새 의존성을 늘리지 않으려고 stdlib만 쓴다."""
    payload = json.dumps({
        "model": REFINE_LLM_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        # 교정은 창의성이 필요 없는 일이다. 온도를 올리면 멀쩡한 문장을 건드린다.
        "options": {"temperature": 0},
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{REFINE_LLM_URL.rstrip('/')}/api/chat",
        data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REFINE_LLM_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
        return (body.get("message") or {}).get("content")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        logger.warning(f"⚠️ LLM 교정 호출 실패 — 원문 유지: {e}")
        return None


def _ask_llm(prompt: str) -> str | None:
    """설정된 경로로 LLM에 묻는다. 어느 쪽이든 실패하면 None(원문 유지)."""
    if REFINE_LLM_BACKEND == "local":
        return _ask_local(prompt)
    return _ask_ollama(prompt)


def _build_prompt(segments: list[dict], start: int, end: int, terms: str | None) -> str:
    """
    고칠 구간 앞뒤에 이웃 줄을 같이 붙인다 — **문맥으로 판단하게 하는 것이 목적**이므로
    줄 하나만 떼어 보여주면 이 방식을 쓰는 의미가 없다.
    """
    head = max(0, start - REFINE_LLM_CONTEXT_LINES)
    tail = min(len(segments), end + REFINE_LLM_CONTEXT_LINES)

    lines = []
    for i in range(head, tail):
        speaker = segments[i].get("speaker") or "?"
        mark = "" if start <= i < end else "   (문맥용, 고치지 말 것)"
        lines.append(f"{i}. [{speaker}] {segments[i]['text']}{mark}")

    parts = []
    if terms:
        # build_context_hint가 주는 문자열이라 용어 외에 참석자 이름 등도 섞여 있다.
        # "용어 목록"이라고 이름 붙이면 모델이 그 형식을 기대하므로 사실대로 쓴다.
        parts.append(f"참고 정보(회의 맥락·용어. 억지로 끼워넣지 말 것):\n{terms}\n")
    parts.append("회의록:\n" + "\n".join(lines))
    parts.append(f"\n{start}번부터 {end - 1}번까지 중에서 잘못 인식된 단어만 고쳐라.")
    return "\n".join(parts)


def correct_transcript(segments: list[dict], terms: str | None = None) -> int:
    """
    세그먼트의 text를 제자리에서 교정한다. 고친 개수를 반환.

    고친 줄에는 text_original(원문)과 llm_corrected=True를 남긴다 —
    사람이 검토하거나 되돌릴 수 있어야 하고, 나중에 이 기능의 효과를 재려면
    무엇이 바뀌었는지 알아야 한다.
    """
    if not REFINE_LLM_ENABLED or not segments:
        return 0

    corrected = 0
    rejected = 0
    for start in range(0, len(segments), REFINE_LLM_BATCH):
        end = min(start + REFINE_LLM_BATCH, len(segments))
        raw = _ask_llm(_build_prompt(segments, start, end, terms))
        if raw is None:
            return corrected     # LLM이 죽었으면 남은 배치도 마찬가지 — 조용히 중단

        for item in _parse_corrections(raw):
            try:
                index = int(item["i"])
                new_text = str(item["text"]).strip()
            except (KeyError, TypeError, ValueError):
                continue
            # 이 배치 밖을 고치려 들면 무시 — 문맥용으로 보여준 줄은 건드리면 안 된다
            if not (start <= index < end) or not new_text:
                continue

            old_text = segments[index]["text"]
            if new_text == old_text:
                continue

            # 모델을 믿지 않고 코드로 막는다. 문장을 다시 썼거나 내용을 넣고 뺀 것으로
            # 보이면 거부한다 — 전사가 조금 틀린 것보다 내용이 바뀌는 쪽이 훨씬 나쁘다.
            ratio = _edit_ratio(old_text, new_text)
            length_ratio = len(new_text) / max(len(old_text), 1)
            if ratio > REFINE_LLM_MAX_EDIT_RATIO or not (0.7 <= length_ratio <= 1.4):
                logger.info(
                    f"🚫 LLM 교정 거부(변경 {ratio:.0%}, 길이 {length_ratio:.0%}): "
                    f"{old_text[:40]} → {new_text[:40]}"
                )
                rejected += 1
                continue

            segments[index]["text_original"] = old_text
            segments[index]["text"] = new_text
            segments[index]["llm_corrected"] = True
            corrected += 1
            logger.info(f"✏️ LLM 교정: {old_text[:50]} → {new_text[:50]}")

    logger.info(
        f"🧠 LLM 문맥 교정: {corrected}개 반영"
        + (f", {rejected}개 거부(과도한 수정)" if rejected else "")
    )
    return corrected
