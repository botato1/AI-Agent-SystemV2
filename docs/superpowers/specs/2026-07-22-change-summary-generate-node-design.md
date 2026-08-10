# 모순 해결 변경요약 생성 노드 — 설계

## 배경

`backend/routers/contradiction_router.py`의 `resolve_contradiction_api`는 모순을 `change_acknowledged`(변경 인지함)로 처리할 때 `contradiction_crud.create_change_summary_draft(...)`로 `ChangeSummaryDraft` row를 `generation_status="pending"` 상태로만 만들고 끝난다 (TODO 주석: "LLM 기반 변경요약 실제 생성은 후속 작업"). 실제 요약 텍스트(`generated_summary`)를 채우는 로직이 없어 기능명세 #22가 부분구현 상태다.

`ChangeSummaryDraft` 모델은 이미 `generation_status IN ('pending','processing','completed','failed')` 상태머신으로 설계되어 있고, `GET /contradictions/{id}/change-summary`라는 별도 폴링 엔드포인트도 이미 존재한다. 이는 응답을 동기로 기다리는 게 아니라 **백그라운드에서 생성하고 프론트가 폴링하는 구조**로 처음부터 설계된 것 — AI Chat 답변 생성 노드(동기, HTTP 응답에 바로 포함)와는 다르게, `contradiction_detect_node`/`meeting_postprocess_node`와 같은 "백그라운드 fire-and-forget" 패턴을 따른다.

## 스코프

**포함**: `ChangeSummaryDraft`를 읽어 `generated_summary`/`generation_status`/`generation_error`/`model_name`을 LLM으로 채우는 노드.

**제외 (지수 파트)**: `resolve_contradiction_api`가 `create_change_summary_draft` 호출 시 `meeting_summary_id`/`room_id`/`base_summary_snapshot`을 채우지 않는 누락이 있음을 확인했으나, 이건 라우터 레이어(지수 파트) 문제로 이번 스코프에서 제외한다. `base_summary_snapshot`은 현재 항상 `None`일 수 있으므로 노드는 이를 **선택적(optional) 컨텍스트**로만 다룬다 (없으면 "추가 맥락 없음"으로 프롬프트 처리).

## 아키텍처

단일 노드 그래프. `contradiction_detect_node`/`meeting_postprocess_node`와 동일하게 노드가 자체 `SessionLocal()`을 열어 draft row를 직접 읽고 쓴다 (AI Chat 노드와 달리 — 이건 백그라운드 트리거라 호출부에 동기로 값을 반환할 필요가 없음).

### 신규 파일

- `backend/graphs/nodes/change_summary_generate.py` — `change_summary_generate_node(state: ContradictionResolutionState) -> dict`
- `backend/graphs/change_summary_graph.py` — `build_change_summary_graph()`, 모듈 레벨 `change_summary_graph`, 헬퍼 `run_change_summary_generation(*, contradiction_id: str, workspace_id: str, category_id: str) -> dict`

### 변경 파일

- `backend/db/crud/contradiction_crud.py` (내 파트) — `update_change_summary_draft(db, contradiction_id, **fields) -> Optional[ChangeSummaryDraft]` 추가 (현재 create/get만 있고 update가 없음)
- `backend/graphs/nodes/__init__.py` — export 추가
- `backend/routers/contradiction_router.py` — `resolve_contradiction_api`에 `BackgroundTasks` 파라미터 추가, draft 생성 직후 `run_change_summary_generation`을 백그라운드로 예약 (트리거 한 줄만 추가, 기존 로직 변경 없음)

## 데이터 흐름

1. **라우터**: `create_change_summary_draft(...)` 호출 직후, `background_tasks.add_task(run_change_summary_generation, contradiction_id=str(contradiction_id), workspace_id=str(workspace_id), category_id=str(contradiction.category_id))`. HTTP 응답은 기존과 동일하게 즉시 반환 (draft는 아직 pending 상태로 응답에 포함 안 됨 — 별도 조회 엔드포인트로 확인).

2. **노드 — 입력 검증 및 멱등성 가드**: `contradiction_crud.get_change_summary_draft(db, contradiction_id)`로 draft 조회. 없으면 `{"error": "draft를 찾을 수 없습니다"}` 반환. `draft.generation_status != "pending"`이면 (이미 처리 중/완료/실패) 그대로 종료 — `meeting_postprocess_node`의 "processing 아닐 때만 진행" 가드와 동일한 의도, 중복 트리거로 인한 재생성 방지.

3. **상태를 processing으로 전환**: `update_change_summary_draft(db, contradiction_id, generation_status="processing")` — 폴링하는 프론트가 "생성 중"임을 알 수 있게.

4. **프롬프트 조립 및 LLM 호출**: `original_reference_text`(기존 내용), `accepted_change_text`(새로 확정된 내용), `base_summary_snapshot`(있으면 참고 맥락, 없으면 "(추가 맥락 없음)")을 프롬프트에 넣어 Ollama에 일반 텍스트 생성 요청 (AI Chat 노드와 동일하게 JSON 강제 안 함 — 요약문 자체가 최종 산출물).

5. **성공**: `update_change_summary_draft(db, contradiction_id, generated_summary=answer, generation_status="completed", model_name=OLLAMA_MODEL)`.

6. **실패** (LLM 호출 예외): `update_change_summary_draft(db, contradiction_id, generation_status="failed", generation_error=str(e))`. AI Chat 노드처럼 대화가 끊기면 안 되는 라이브 응답이 아니므로, 여기선 안내 문구로 폴백할 필요 없이 실패 상태를 그대로 기록하고 프론트가 재시도 UI를 보여주면 된다.

7. 노드는 항상 `{"generated_summary": ..., "generation_status": ..., "change_summary_draft_id": str(draft.id)}` 형태의 dict를 반환.

## 에러 처리

- 다른 두 노드처럼 노드 전체를 try/except로 감싸 예외가 새어나가지 않게 한다. 최종 except 블록에서도 가능하면 draft를 `failed` 상태로 남긴다 (meeting_postprocess_node의 finally 패턴과 동일 — draft가 processing에 영원히 머무르지 않도록).

## 테스트

DB/Ollama 목킹 컨벤션이 없는 코드베이스라, 프롬프트 조립 함수(순수 함수로 분리: `build_summary_prompt(original_text, accepted_text, base_summary) -> str`)만 유닛테스트로 커버하고, 나머지는 AI Chat 노드 때와 동일하게 실제 서버 환경(Docker 이미지)에서 수동 검증한다.
