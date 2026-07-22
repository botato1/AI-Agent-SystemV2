# STT 모듈 프론트엔드 연동 가이드

> 이 문서 하나로 STT 관련 화면을 전부 구현할 수 있도록 작성됨.
> 작동하는 레퍼런스 구현이 `backend/modules/stt/test_client/realtime_test.html`에 있음 —
> 모든 API 호출과 오디오 처리 코드를 그대로 참고/복사 가능.
> 담당: 이준오 (STT)
> 마지막 갱신: 2026-07-21 (전역 프로필/rename 전파/C-4 재분석 실서버 라이브 검증 완료)

## 0. 지금 당장 접속 주소가 필요하다면

**서버 주소를 코드에 하드코딩하지 말 것.** 포트가 최근에도 8001→8002로 한 번 바뀌었고,
아직 외부 IP:포트가 완전히 열리지 않아서 임시로 Cloudflare 터널 주소(매번 랜덤하게 바뀜)를
쓰고 있음. UI 화면에도 `realtime_test.html`처럼 **서버 주소를 입력/설정 가능한 값**으로 두고,
지금 유효한 주소는 이준오한테 직접 물어볼 것 (Slack/카톡으로 그때그때 공유).

## 1. 시스템 개요

실시간 회의 음성인식 서버. 브라우저 마이크 오디오를 WebSocket으로 스트리밍하면
실시간 자막(잠정→확정)과 화자 이름이 붙은 회의록이 만들어진다.
회의 종료 후엔 서버가 자동으로 정밀 재분석(C-4)을 돌려 회의록 품질을 보정한다.

용어:
- **전역 프로필**: 최초 1회 등록하는 영구 목소리 지문. 이후 모든 회의에서 재사용.
- **세션 등록**: 이번 회의(session_id)에만 쓰는 임시 목소리 등록. 전역 프로필 없는 게스트용.
- **닫힌 집합**: 참석자 명단이 확정된 상태의 화자 인식 (정확도 높음). 열린 집합은 명단 없이 자동감지(SPEAKER_1, 2... 라벨).
- **partial/final**: 잠정 자막(계속 갱신됨) / 확정 자막(고정).

## 2. 사용자 흐름 (화면 순서)

```
[최초 1회, 사용자별]
  프로필 등록 화면: 표준 문장 표시 → 읽으면 자동 녹음 종료 → 이름 자동 인식 → 등록
     (이름 오인식 시: 직접 입력 폴백 / 등록 후에도 이름 수정 가능)

[매 회의]
  ① 회의 방식 선택: "한 대의 PC(공용 마이크)" vs "각자 PC" (후자는 백엔드 미구현 — UI만 예비)
  ② 참석자 선택: 전역 프로필 목록에서 체크박스로 선택
     + 프로필 없는 게스트가 있으면 세션 등록 진행 (둘은 합산됨)
  ③ 회의 진행: 실시간 자막 (잠정=흐릿하게, 확정=진하게 + 화자 이름 태그)
  ④ 종료: "회의 종료" 버튼 → 서버가 마지막 발언 처리 → session_end 수신 후 연결 닫기
  ⑤ 회의록 아카이브: 저장된 회의 목록/상세 조회, 오디오 다시 듣기
```

## 3. 오디오 입력 규격 (모든 오디오 전송의 공통 규칙)

서버는 **16kHz, mono, PCM16LE(리틀엔디언 16비트 정수)** 만 받는다.
브라우저 마이크는 보통 44.1k/48kHz Float32라 변환이 필요:

```js
// 브라우저 샘플레이트 → 16kHz 다운샘플
function downsampleTo16k(float32Array, inputSampleRate) {
  if (inputSampleRate === 16000) return float32Array;
  const ratio = inputSampleRate / 16000;
  const out = new Float32Array(Math.floor(float32Array.length / ratio));
  for (let i = 0; i < out.length; i++) out[i] = float32Array[Math.floor(i * ratio)];
  return out;
}
// Float32 → PCM16LE ArrayBuffer
function float32ToPCM16LE(f32) {
  const buf = new ArrayBuffer(f32.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buf;
}
```

주의: 마이크 권한은 **https 또는 localhost에서만** 열림. 개발 중엔 localhost 접속 또는 터널 필요.

## 4. REST API

베이스: `http://<서버주소>/api` (`<서버주소>`는 0번 항목 참고 — 현재 고정 IP:포트 아님).
오디오 업로드는 전부 `Content-Type: application/octet-stream` 바디에 PCM16 바이너리.

### 전역 프로필

| 메서드/경로 | 설명 |
|---|---|
| `GET /profiles/script` | 등록 시 읽을 표준 문장. `{"script": "안녕하세요, OOO입니다. ..."}` — UI는 OOO를 "(본인 이름)"으로 치환해 표시. 발음 다양성 확보를 위해 10~12초 분량이므로 **하드코딩하지 말고 이 API로 받아 표시할 것** |
| `POST /profiles` (바디=오디오) | 등록. 문장 첫머리 "안녕하세요 OOO입니다"에서 이름 자동 추출. 같은 이름 재등록=목소리 갱신(의도된 동작) |
| `POST /profiles?speaker_name=이름` | 이름 자동 인식 실패 시 수동 지정 재요청 (직전 녹음 오디오 재사용 가능) |
| `GET /profiles` | `{"names": ["가동현", "이준오", ...]}` — 참석자 선택 체크박스의 데이터 소스 |
| `DELETE /profiles/{이름}` | 프로필 삭제 |
| `PATCH /profiles/{이름}/rename?new_name=새이름` | 이름 오인식 수정 (목소리 지문은 유지) |

`POST /profiles` 응답:
```json
// 성공
{"status": "success", "speaker_name": "이준오", "detected_text": "안녕하세요 이준오입니다 ...",
 "name_extraction_failed": false, "registered_names": ["이준오"]}
// 이름 인식 실패 → 수동 입력 UI 표시할 것
{"status": "error", "detected_text": "안녕 이거 되나요", "name_extraction_failed": true, "message": "..."}
// 오디오 문제 (너무 짧음 등)
{"status": "error", "message": "오디오가 너무 짧음 (0.3s < 0.5s). 다시 녹음해줘."}
```

### 세션 등록 (게스트용)

전역 프로필과 API 모양이 거의 같고, 경로에 session_id가 붙는 차이:
`POST /enroll/{session_id}`, `GET /enroll/{session_id}`, `DELETE /enroll/{session_id}`,
`PATCH /enroll/{session_id}/rename?old_name=&new_name=`.
게스트는 "안녕하세요 OOO입니다" 한 마디면 충분 (전역 등록처럼 긴 문장 불필요).
동명이인은 자동으로 "이준오2"처럼 넘버링됨.

### 회의록

| 메서드/경로 | 설명 |
|---|---|
| `GET /meetings` | 저장된 회의 목록 (최신순). `{"count": N, "meetings": [{meeting_id, session_id, started_at, ended_at, status, speaker_mode, refined, segment_count}]}` |
| `GET /meetings/{meeting_id}` | 회의록 상세. `segments`(아래 공통 스키마 배열), `refined`(정밀 재분석 완료 여부), `realtime_segments`(재분석 전 원본, 비교용) 포함 |
| `POST /meetings/{meeting_id}/refine` | 정밀 재분석 수동 재실행 (자동 실행이 실패했을 때만 필요) |
| `PATCH /meetings/{meeting_id}/segments/{index}` | 세그먼트 텍스트 수동 수정 (바디: `{"text": "고친 내용"}`). 2026-07-22 추가 |
| `GET /meetings-files/{meeting_id}/audio.wav` | 회의 오디오 원본 (다시 듣기 플레이어 소스) — /api 접두사 없음 주의. **각자 PC 모드 회의는 이 파일이 없음**(`audio_file: null`) |

`status`: `recording`(진행 중) / `completed`(정상 종료) / `disconnected`(끊김 — 그래도 기록은 보존됨).
`refined`: 회의 종료 직후엔 false, 백그라운드 재분석(수 분)이 끝나면 true로 바뀜 → **아카이브 화면에서 "정밀 분석 중..." 배지로 표시하고 폴링/새로고침 권장**.

## 5. WebSocket 프로토콜 (회의 진행 화면의 핵심)

### 연결

**① 한 대의 PC(공용 마이크)**:
```
ws://<서버주소>/api/ws/stt/{session_id}?attendees=이준오,가동현
```

**② 각자 PC (2026-07-22 추가)**: 참가자마다 자기 브라우저에서 각자 접속, `participant_name`으로 본인 이름을 넣음. **같은 `session_id`로 접속해야 하나의 회의로 병합됨**:
```
ws://<서버주소>/api/ws/stt/{session_id}?participant_name=이준오
```
- 이미 본인이 누군지 알고 접속하는 거라 화자 식별 자체가 없음 — 그 이름으로 바로 라벨링됨
- 여러 명의 오디오를 하나로 믹싱하는 건 지원 안 함 — 텍스트(세그먼트)만 시간순으로 병합됨. 그래서 이 모드로 진행한 회의는 **오디오 다시 듣기, C-4 정밀 재분석이 없음** (실시간 인식 결과가 곧 최종본)
- 마지막 참가자가 "end"를 보내거나 연결이 끊길 때만 회의 전체가 종료 처리됨 (한 명이 먼저 나가도 회의는 계속됨)

(`<서버주소>`가 https 터널이면 `wss://`로)
- `session_id`: 회의방 식별자 (프론트가 생성, 예: UUID). 재연결 시 같은 값 사용하면 세션 등록 유지됨.
- `attendees` (선택): 참석자 선택 화면에서 체크한 전역 프로필 이름들 (콤마 구분, URL 인코딩).
- 화자 인식 모드는 자동 결정: 전역(attendees) + 세션 등록 **합산** → 닫힌 집합. 둘 다 없으면 자동감지.

### 보내기
- 마이크 오디오: **바이너리 프레임**으로 PCM16 조각을 계속 전송 (권장: ScriptProcessor 4096 샘플 단위)
- 회의 종료: **텍스트 프레임 `"end"`** 전송 → 서버가 잔여 버퍼 처리 후 아래 session_end 응답.
  **그냥 close()하면 안 됨** (마지막 발언은 저장되지만 화면에는 못 받음)

### 받기 (JSON 텍스트 프레임 3종)

```json
// 1) partial — 잠정 자막. 이전 partial을 대체하며 계속 갱신 (회색/이탤릭 표시 권장)
{"session_id": "...", "type": "partial", "confirmed_text": "오늘 회의는", "tentative_text": "여기까지 하고..."}

// 2) final — 확정 자막. 화면에 고정 append하고 잠정 표시는 제거
{"session_id": "...", "type": "final", "chunk_offset_sec": 12.5, "speaker": "이준오",
 "latency_sec": 2.3, "final": {"segments": [/* 아래 공통 스키마 */]}}

// 3) session_end — "end" 보낸 뒤 수신. 이걸 받으면 close()
{"session_id": "...", "type": "session_end", "meeting_id": "team1_20260717-050000"}
```
`meeting_id`를 저장해두면 종료 직후 회의록 상세 화면으로 바로 이동 가능.

## 6. 세그먼트 공통 스키마 (실시간 final과 회의록 segments 동일)

| 필드 | 타입 | 의미 |
|---|---|---|
| `start`, `end` | float | 회의 시작 기준 초 |
| `text` | string | 발화 텍스트 |
| `speaker` | string | 화자 이름 (닫힌 집합) 또는 SPEAKER_N (자동감지) |
| `confident` | bool | false면 인식 신뢰도 낮음 — **흐린 색/밑줄로 구분 표시 권장** |
| `user_edited` | bool | 사용자가 수정한 세그먼트인지 (회의록 수정 기능용, 현재는 항상 false) |

(실시간 final에는 진단용 `avg_logprob`, `no_speech_prob`가 추가로 붙을 수 있음 — 무시해도 됨)

## 7. 엣지 케이스 / UX 규칙

- **이름 오인식은 정상 상황**: 발음이 비슷한 이름("준오"↔"준호")은 STT 한계상 틀릴 수 있음.
  등록 성공 후에도 항상 "이름 수정" 버튼을 노출할 것 (rename API, 재녹음 불필요).
  **주의**: "방금 등록한 사람"뿐 아니라 `GET /profiles`로 **불러온 기존 프로필 목록의 각 이름에도**
  개별 수정 버튼을 달아야 함 (레퍼런스 구현에서 처음엔 방금 등록한 경우에만 버튼이 떠서
  기존 프로필을 못 고치는 버그가 있었음 — 참석자 목록 렌더링 시 이름마다 수정 버튼 포함시킬 것).
- **참석자 체크박스는 선택 상태를 눈에 보이게 표시할 것**: 체크만 하고 아무 피드백이 없으면
  사용자가 선택이 반영됐는지 헷갈려함. "선택된 참석자: 이준오, 가동현" 같은 실시간 요약 텍스트 권장.
- **2026-07-21 라이브 검증 완료**: 회의 진행 중 이름을 수정하면 그 즉시 화자 라벨이 새 이름으로
  바뀌는 것 확인됨(rename 실시간 전파). C-4 재분석의 익명 라벨→실명 매핑도 충분히 긴 발화
  (30초+)에서 정상 동작 확인됨. 단, 발화가 극단적으로 짧으면(1~2초) 매핑을 포기하고 익명
  라벨(SPEAKER_N)을 유지하는 게 의도된 안전장치임 — UI에서 이런 세그먼트를 만나면 에러가
  아니라 정상 케이스로 처리할 것(익명 라벨도 그대로 표시).
- **등록 녹음은 자동 종료**: 침묵 감지로 자동 종료되므로 "정지" 버튼 불필요.
  전역 등록(긴 문장)은 침묵 판정을 길게 잡아야 문장 중간 호흡에 안 끊김 (레퍼런스: 1.5초/최대 25초).
- **재연결**: 연결이 끊겨도 같은 session_id로 재접속하면 세션 등록이 유지됨.
  재접속 시 attendees도 같은 값으로 다시 붙일 것.
- **화자 오배정 안내**: 실시간 화자 표시는 1차 추정이라 가끔 틀림. 회의 종료 후
  정밀 재분석이 보정하므로, "실시간 표시는 잠정적이며 최종 회의록에서 보정됩니다" 안내 권장.
- **인증 없음(현재)**: session_id를 아는 누구나 접속 가능. 팀 로그인(E-1) 연동 예정.

## 8. 아직 백엔드에 없는 것 (UI 설계 시 참고)

- 요약/액션아이템 (A-5) — LLM 담당(승주) 영역
- 인증(session_id만 알면 접속 가능) — 팀 로그인 연동 예정

("각자 PC" 모드와 회의록 세그먼트 수정 API는 2026-07-22에 추가됨 — 위 4/5번 섹션 참고)
