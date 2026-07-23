# AI Chat 답변 생성 노드 — 설계

## 배경

`backend/routers/ai_chat_router.py`의 `send_ai_chat_message` 엔드포인트는 `_generate_ai_response(session_id, question)`를 호출하는데, 이 함수는 현재 `raise NotImplementedError(...)` 스텁이라 호출 시 항상 503을 반환한다 (기능명세 #26 "AI 질문 및 답변 생성" 미구현 상태).

`backend/graphs/states/ai_chat_state.py`에 이미 `AIChatState` TypedDict가 정의되어 있고, `contradiction_detect_node`(`backend/graphs/nodes/contradiction_detect.py`) / `meeting_postprocess_node`(`backend/graphs/nodes/meeting_postprocess.py`)와 동일한 "단일 노드가 검색→생성→저장을 전부 수행" 패턴을 따르는 것이 코드베이스 컨벤션과 일치한다.

## 목표

사용자가 채팅방별 AI Chat 세션에서 질문을 보내면, 워크스페이스에 업로드된 문서와 회의 내용을 RAG로 검색해서 근거 기반 답변을 생성하고, 답변과 근거자료(sources)를 저장한다.

## 아키텍처

단일 노드 그래프. 멀티노드 분리는 고려했으나 기각 — 이 코드베이스의 기존 두 그래프(`contradiction_graph.py`, `meeting_postprocess_graph.py`) 모두 단일 노드이고, 이번 노드의 하위 단계(검색/생성/저장)도 서로 독립적으로 재사용될 일이 없어 분리 시 이점 없이 복잡도만 늘어난다.

### 신규 파일

- `backend/graphs/nodes/ai_chat_answer.py` — `ai_chat_answer_node(state: AIChatState) -> dict`
- `backend/graphs/ai_chat_graph.py` — `build_ai_chat_graph()`, 모듈 레벨 `ai_chat_graph`, 헬퍼 `run_ai_chat_answer(*, session_id, workspace_id, category_id, user_message, chat_history=None) -> dict`
  (기존 `run_contradiction_detection` / `run_meeting_postprocess` 헬퍼와 동일 형태)

### 변경 파일

- `backend/routers/ai_chat_router.py` — `_generate_ai_response` 스텁 삭제, `send_ai_chat_message`가 `run_ai_chat_answer(...)`를 동기 호출하도록 교체 (백그라운드 아님 — 채팅 응답은 요청-응답 사이클 안에서 바로 받아야 함)
- `backend/graphs/nodes/__init__.py` — `ai_chat_answer_node` export 추가

## 데이터 흐름

1. **입력 검증**: `state["session_id"]`, `workspace_id`, `category_id`, `user_message` 필수 확인. 없으면 `{"error": "..."}` 반환 (다른 두 노드와 동일 컨벤션).

2. **RAG 검색** (문서 + 회의 둘 다, 사용자 확정):
   `search_hybrid()`는 `collection_name`에 단일 문자열 또는 `None`(전체 4개 컬렉션)만 받고 리스트는 못 받으므로, `DOCUMENT_COLLECTION`과 `MEETING_COLLECTION`에 각각 별도 호출 후 직접 병합한다.

   ```python
   TOP_K_PER_COLLECTION = 5
   TOP_K_FINAL = 5

   doc_results = search_hybrid(
       query_text=user_message, workspace_id=workspace_id, category_id=category_id,
       top_k=TOP_K_PER_COLLECTION, collection_name=DOCUMENT_COLLECTION,
   )
   meeting_results = search_hybrid(
       query_text=user_message, workspace_id=workspace_id, category_id=category_id,
       top_k=TOP_K_PER_COLLECTION, collection_name=MEETING_COLLECTION,
   )
   candidates = sorted(doc_results + meeting_results, key=lambda r: r["score"], reverse=True)[:TOP_K_FINAL]
   ```
   (`search_hybrid`가 반환하는 `score`는 semantic 0.7 + keyword 0.3 가중합, 이미 내림차순 정렬된 상태 — 병합 후 재정렬만 하면 됨.)

3. **검색 결과 0건**: LLM 호출 없이 고정 문구로 즉시 응답 저장 후 반환 (환각 방지 + 지연시간/비용 절감).
   `"업로드된 자료에서 관련 내용을 찾지 못했습니다. 다른 표현으로 다시 질문해주시겠어요?"`

4. **검색 결과 있음 — LLM 답변 생성**:
   - 각 candidate의 `id`(chroma_id)로 `content_chunk_crud.get_chunk_by_chroma_id(db, candidate["id"])`를 호출해 Postgres `ContentChunk` row를 역참조. 못 찾으면(고아 데이터) 스킵 — `contradiction_detect_node`와 동일 처리.
   - 프롬프트에 (a) 검색된 청크 본문들, (b) `chat_history`의 최근 N턴(N=6, 최근 3턴 왕복), (c) 현재 질문을 넣어 Ollama에 일반 텍스트 생성 요청 (다른 두 노드와 달리 `format: "json"` 강제 안 함 — 채팅 답변은 자연어 그대로 노출).
   - 프롬프트에는 "근거 자료에 없는 내용은 답하지 말고 모른다고 답하라"는 지시를 포함해 환각을 최대한 억제한다 (완벽한 보장은 아니므로 3번의 규칙 기반 zero-result 처리가 1차 방어선, 이 지시문은 2차 방어선).

5. **저장**:
   - `ai_chat_crud.add_message(db, session_id=session_id, role="assistant", content=answer)`
   - 유효한 청크마다 `AiMessageSource` 딕셔너리 조립: `{"source_type": "content_chunk", "file_id": chunk.file_id, "chunk_id": chunk.id, "similarity_score": candidate["score"], "display_order": i}` → `ai_chat_crud.add_sources(db, assistant_message.id, sources)`
   - `code_fact` 소스 타입은 아직 코드베이스에 `code_fact` 모델/CRUD 자체가 없어(레포 전체 검색으로 확인됨) 이번 스코프에서 제외.

6. **반환 state**: `answer`, `answer_model_name`, `chunk_search_results`(candidates), `assistant_message_id`, `retrieved_sources`, `saved_source_ids`.

## 라우터 통합

`send_ai_chat_message`는 오늘처럼 user 메시지를 먼저 저장한 뒤, `run_ai_chat_answer(...)`를 동기 호출한다. 노드가 자체 `SessionLocal()`로 이미 커밋까지 마치므로, 라우터는 `ai_chat_crud.get_session_history(db, session.id)`로 방금 저장된 assistant 메시지를 다시 조회해 응답을 만든다 (라우터의 request-scoped `db` 세션과 노드의 별도 세션 간 read-after-commit이라 정상 조회됨 — 기존 두 그래프도 동일하게 자체 세션을 씀).

## 에러 처리

- Ollama 호출 실패/타임아웃: 500을 던지지 않고 `"지금은 답변을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."`를 assistant 메시지로 저장 (대화 흐름이 끊기지 않게). `state["error"]`에 실제 예외는 로깅용으로 남김.
- `search_hybrid` 자체가 예외를 던지는 경우(Chroma 장애 등)도 동일하게 fallback 메시지로 처리.
- 다른 두 노드처럼 `try/except`로 감싸 노드 전체가 죽지 않게 한다.

## 테스트

이 코드베이스에 DB/Chroma/Ollama 목킹 컨벤션이 없어(`test_contradiction_graph.py` 참조), 이번에도 순수 로직만 유닛 테스트로 커버한다:
- 문서+회의 검색 결과 병합/정렬 로직
- 검색 결과 0건일 때 고정 응답 분기
- 프롬프트 조립 함수(청크/히스토리 포맷팅)

그래프 실제 실행(Ollama 호출 포함)은 기존 컨벤션대로 수동 검증.

## 스코프 밖

- `code_fact` 소스 타입 (모델/CRUD 자체가 미구현)
- 시맨틱 캐싱, 스트리밍 응답
- `chat_history`를 라우터에서 어떻게 조립해 `run_ai_chat_answer`에 넘길지의 정확한 최근 N개 절단 로직은 구현 계획 단계에서 확정
