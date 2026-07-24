"""figure_cls.pt 모델이 실제로 어떤 클래스로 학습됐는지 확인합니다.

실행: PYTHONPATH=. python3 doc_processor/classifiers/check_model_classes.py
"""
from pathlib import Path
from ultralytics import YOLO

MODEL_PATH = Path(__file__).parent / "figure_cls.pt"

model = YOLO(str(MODEL_PATH))
print("모델 경로:", MODEL_PATH)
print("클래스 목록 (names):", model.names)
