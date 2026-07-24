from typing import List, Optional
from pydantic import BaseModel, Field
# CommonDocumentSchema는 팀 공통 14개 필수 키를 담고 있는 부모 클래스입니다.
from backend.schemas.common_schema import CommonDocumentSchema


# 1. transcription 배열 안에 들어가는 개별 대사 하나의 구조
class TranscriptionItem(BaseModel):
    start: float     # 🔄 str에서 float로 변경 (오디오 싱크 및 pipeline.py의 round 연산 호환성 확보)
    end: float       # 🔄 str에서 float로 변경
    speaker: str     # 화자 구분 (예: SPEAKER_00)
    text: str        # STT가 추출한 실제 텍스트
    user_edited: bool = False  # ⭐ 준오님 파트의 핵심 기능: 줄 단위 수정 여부 추적 필수 키 추가!


# 2. STT 처리 관련 모듈 특화 메타데이터 (조원분이 확장해두신 좋은 필드들을 그대로 유지했습니다)
class STTMetadata(BaseModel):
    duration_sec: float              # 실제 원본 오디오 길이, 초 단위
    original_format: str             # 원본 파일 확장자 (예: m4a, mp3)
    model_used: str                  # 사용한 STT 모델명 (예: large-v3-turbo)
    vad_applied: bool                # VAD 적용 여부
    initial_prompt_applied: bool     # initial prompt 적용 여부
    total_time_sec: float            # STT 처리에 걸린 시간
    compute_type: str                # 연산 타입, 예: int8
    original_file_url: Optional[str] = None


# 3. 최종 STT 결과 구조 (팀 공통 스키마를 상속받아 14개 공통 키를 자동으로 포함합니다)
class STTResultSchema(BaseModel):
    id: str
    title: str

    type: str = "consultation_audio"
    source: str = "voice"

    room_id: Optional[str] = None
    conversation_id: Optional[str] = None

    content: Optional[str] = None
    summary: Optional[str] = None

    transcription: list[TranscriptionItem] = Field(default_factory=list)
    metadata: Optional[STTMetadata] = None

    language: str = "ko"
    created_at: str
    status: str = "processed"
    error: Optional[str] = None