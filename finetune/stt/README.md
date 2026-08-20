# STT 파인튜닝 — 데이터 수집 및 평가 가이드

Whisper(large-v3)를 우리 팀 개발 용어에 특화시키기 위한 LoRA 파인튜닝 준비 자료.
담당: 이준오 (STT)

## 왜 하나

hotwords(힌트 단어 주입)를 제거하고 파인튜닝으로 전환하기로 결정함 (2026-07-15).
"레이턴시", "임베딩" 같은 개발 용어가 "레이턴 시", "임베 딩"처럼 깨지는 오인식을
모델 수준에서 줄이는 게 목표. 일반 한국어 성능은 유지가 전제.

## 데이터 소스 3개

| 소스 | 용도 | 목표량 | 상태 |
|---|---|---|---|
| ① 팀원 낭독 녹음 | 용어 밀도 최고, 라벨 공짜 | 6명 × 40문장 ≈ 2시간 | `recording_script.txt` 준비됨 |
| ② 실제 팀 회의 | 진짜 분포의 데이터 | 3~5시간 누적 | 회의록 저장 기능이 자동 수집 중 |
| ③ AI Hub 공개 데이터 | 일반 성능 유지(과적합 방지) | 5~10시간 | 신청 필요 (아래 절차) |

---

## ① 낭독 녹음 가이드 (팀원 전원)

1. `recording_script.txt`의 40문장을 **한 문장당 하나의 파일**로 녹음
2. 조용한 방에서, 평소 회의하듯 자연스러운 속도로 (또박또박 낭독체 금지 — 회의 말투)
3. 파일명 규칙: `{이름}_{문장번호 3자리}.wav` — 예: `이준오_001.wav`, `가동현_027.wav`
4. 아무 포맷으로 녹음했으면 제출 전에 변환:
   ```bash
   ffmpeg -i 원본.m4a -ar 16000 -ac 1 이준오_001.wav
   ```
5. 완료 후 NAS의 `finetune_data/recordings/` 폴더에 업로드 (폴더는 추후 지정)

소요 시간: 1인당 15~20분.

## ② 실제 회의 데이터 (자동 수집됨)

우리 시스템으로 회의를 하면 `backend/modules/stt/meetings/`에 오디오와
정밀 재분석된 회의록이 자동 저장됨. 이후 회의록 수정 UI(D-3)가 생기면
팀원이 교정한 텍스트가 곧 학습 라벨이 됨. **지금은 그냥 시스템으로 회의만 하면 됨.**

## ③ AI Hub 신청 절차 (이준오 담당, 즉시)

1. https://aihub.or.kr 회원가입 (학교 이메일 권장)
2. 데이터 검색: "회의 음성", "한국어 자유대화 음성" 등 회의/대화체 데이터셋 검색
3. 원하는 데이터셋 페이지에서 [활용 신청] — 용도에 "학술 연구(캡스톤 프로젝트)" 기재
4. 승인까지 보통 1~3일 → 승인되면 로컬로 다운로드 후 NAS 업로드
5. 주의: 라이선스상 재배포 금지 — NAS 팀 폴더 안에서만 사용

---

## 평가 (베이스라인 → 파인튜닝 후 비교)

### 1. 매니페스트 생성 (녹음 파일 → 정답 텍스트 매핑)
```bash
cd finetune/stt
python make_manifest.py --recordings /path/to/recordings --output manifest.jsonl
```

### 2. 평가 실행 (GPU 서버에서, stt venv 활성화 후)
```bash
python evaluate_wer.py --manifest manifest.jsonl --terms terms.txt --output baseline_report.json
```

측정 지표:
- **WER** (단어 오류율) / **CER** (글자 오류율) — 전반적 인식 품질
- **용어 재현율** — `terms.txt`의 핵심 용어가 제대로 인식된 비율 (핵심 지표)

### 3. 규칙
- **파인튜닝 전에 반드시 베이스라인부터 측정** — `baseline_report.json`을 커밋해둘 것
- 테스트셋(전체의 20%)은 학습에 절대 사용 금지, 한 번 정하면 변경 금지
- 파인튜닝 후 같은 명령으로 재측정 → 두 리포트 비교가 곧 성과 지표 (논문 재료)

## ④ LoRA 파인튜닝 실행

### 1. AI Hub 매니페스트 생성 (zip을 재압축 해제하지 않고 경로만 인덱싱)
```bash
cd finetune/stt
python make_manifest_aihub.py --data-dir /path/to/Training --output manifest_aihub.jsonl
```

### 2. 학습 실행 (GPU 서버, stt_venv 활성화 후)
```bash
python train_lora.py \
  --manifests manifest.jsonl manifest_aihub.jsonl \
  --output-dir ./lora_checkpoints \
  --epochs 3 --batch-size 4
```
- `manifest.jsonl`(팀원 녹음)과 `manifest_aihub.jsonl`(AI Hub)을 함께 넣으면 두 소스를 합쳐서 학습함
- `evaluate_wer.py`에 쓰는 테스트셋(20%)은 절대 이 매니페스트에 섞지 말 것
- 완료되면 `lora_checkpoints/final_adapter/`에 어댑터 저장됨 (베이스 모델 전체가 아니라 LoRA 가중치만, 용량 작음)

### 3. 파인튜닝 후 재평가
```bash
python evaluate_wer.py --manifest manifest.jsonl --terms terms.txt --output finetuned_report.json
```
`baseline_report.json`과 비교해서 WER/CER/용어 재현율 개선폭 확인.

## 파일 목록

| 파일 | 설명 |
|---|---|
| `recording_script.txt` | 낭독용 40문장 (사람이 읽는 용도) |
| `script_sentences.json` | 같은 문장의 기계용 버전 (매니페스트 생성에 사용) |
| `terms.txt` | 용어 재현율 평가 대상 핵심 용어 목록 |
| `make_manifest.py` | 팀원 녹음 파일명 → 정답 텍스트 매핑 생성 |
| `make_manifest_aihub.py` | AI Hub 라벨/오디오 zip → 매니페스트 생성 (압축 해제 없이 경로만 인덱싱) |
| `evaluate_wer.py` | WER/CER/용어 재현율 측정 |
| `train_lora.py` | Whisper large-v3 LoRA 파인튜닝 실행 |
