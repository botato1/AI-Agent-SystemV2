# topic_match 모델 배포 파이프라인 (병합 → 변환 → 등록)

82서버는 컨테이너가 2개로 나뉘어 있다는 게 핵심.

- `172.17.0.3` — venv-finetune(학습/eval_adapter), venv-trans(GGUF 변환). GPU 있음. ollama 바이너리는 없음.
- `172.17.0.7` — venv-backend. ollama 바이너리는 여기만 있음.
- 홈 디렉토리 `.zsh_history`는 두 컨테이너가 공유돼서, `history`에 상대방 컨테이너 명령이 섞여 보일 수 있음 (헷갈리지 말 것).
- `~/nas_private/AI-Agent-SystemV2/models/`는 두 컨테이너 다 접근 가능한 공유 경로 — 컨테이너 간 파일 전달은 반드시 여기를 거쳐야 함.

버전 번호(`v{N}`)만 바꿔서 그대로 재사용하면 됨.

## 1) LoRA 병합 (172.17.0.3, venv-finetune)
```bash
cd ~/AI-Agent-SystemV2/finetune
python merge_lora.py --lora_adapter ./model_output_v{N}/lora_adapter --out ./model_output_v{N}/merged_model
```

## 2) GGUF 변환 (172.17.0.3, venv-trans로 전환)
```bash
deactivate
source ~/venv-trans/bin/activate
cd ~/AI-Agent-SystemV2/finetune
python llama.cpp/convert_hf_to_gguf.py ./model_output_v{N}/merged_model --outfile ./model_output_v{N}/model_unified_v{N}.gguf --outtype bf16
```

## 3) 공유 NAS로 복사 (172.17.0.3에서)
```bash
cp ~/AI-Agent-SystemV2/finetune/model_output_v{N}/model_unified_v{N}.gguf ~/nas_private/AI-Agent-SystemV2/models/model_unified_v{N}.gguf
```

## 4) Ollama 등록 (172.17.0.7로 이동, venv-backend)
```bash
cat > Modelfile_v{N} <<'EOF'
FROM /home/s202410786/nas_private/AI-Agent-SystemV2/models/model_unified_v{N}.gguf
TEMPLATE {{ .Prompt }}
EOF
ollama create re-call-model1-unified-v{N} -f Modelfile_v{N}
```

`TEMPLATE {{ .Prompt }}`를 꼭 넣어야 함 — 채팅 템플릿 안 씌우고 raw prompt 그대로 넣는 방식이고,
`decision_judgment.py`의 `_ask_topic_match()`와 eval/compare 스크립트들이 전부 이 raw prompt 형식으로
호출하기 때문에 학습 때와 추론 때 프롬프트 형식이 어긋나지 않으려면 반드시 필요함.

## 5) 확인
```bash
ollama run re-call-model1-unified-v{N} "안녕하세요, 정상 작동 확인용 테스트입니다"
```

## 참고: 자주 헤맸던 실수
- NAS 경로는 `nas_data`가 아니라 `nas_private/AI-Agent-SystemV2/models` — `nas_data`는 권한도 없고 원래 안 쓰던 곳.
- `ollama` 커맨드가 "command not found"면 컨테이너를 잘못 들어온 것 (172.17.0.7로 가야 함).
- gguf 파일이 안 보이면 지금 있는 컨테이너의 로컬 경로(`~/AI-Agent-SystemV2/...`)를 찾고 있는 건 아닌지 확인 —
  컨테이너 간 공유는 `~/nas_private/...`뿐이고 `~/AI-Agent-SystemV2`는 컨테이너별 로컬 클론임.
