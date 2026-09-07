#!/usr/bin/env bash
# DeepFilterNet 전용 격리 venv를 만든다. 공유 stt_venv는 절대 건드리지 않는다
# (지난 시도에서 DeepFilterNet이 numpy를 2.5.x -> 1.26.4로 강제 다운그레이드해서
# pyannote-core/scipy와 충돌, 서버 재시작 시 화자분리가 깨질 뻔했다 — IDEAS.md #8).
set -euo pipefail

VENV_DIR="${1:-$HOME/dfn_venv}"

if [ -d "$VENV_DIR" ]; then
  echo "이미 있음: $VENV_DIR (재사용)"
else
  python3 -m venv "$VENV_DIR"
  echo "생성됨: $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip

# deepfilternet은 torch를 의존성으로 선언하지 않는다(설치 후 import 시점에
# ModuleNotFoundError로 드러남). 오디오 한 건 향상시키는 데 GPU 속도가 꼭
# 필요하진 않으므로 가볍고 빠른 CPU 휠을 쓴다.
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# 여기서 numpy가 어떻게 바뀌는지는 이 venv 안에서만 유효하다 — 공유 venv엔
# 영향 없음. 그래도 무슨 일이 벌어지는지 보고 싶으면 --dry-run으로 먼저 확인.
pip install --dry-run deepfilternet scipy numpy || true
echo "--- 위는 dry-run. 실제 설치 진행 ---"
pip install deepfilternet scipy numpy

python -c "from df.enhance import init_df; init_df(); print('✅ DeepFilterNet 로딩 성공')"

deactivate
echo "완료. 사용법: $VENV_DIR/bin/python dfn_enhance.py 입력.wav 출력.wav"
