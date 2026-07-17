import os

import numpy as np

from ..core.config import logger, VOICE_PROFILES_DIR


class GlobalProfileStore:
    """
    모든 회의에서 재사용되는 전역 화자 프로필(목소리 지문) 저장소.

    회의별 임시 등록(enrolled_profiles, 메모리)과 달리 디스크에 영구 보관되어,
    프로그램 최초 사용 시 한 번만 목소리를 등록하면 이후 회의에선
    "참석자 선택"만으로 화자 식별이 가능해진다.

    저장 형식: {VOICE_PROFILES_DIR}/{이름}.npy — 이름 하나당 임베딩 벡터 하나.
    같은 이름으로 다시 등록하면 덮어씀(재등록) — 목소리가 변했거나(감기 등)
    마이크 환경이 바뀌었을 때 갱신하는 용도.
    """

    def __init__(self, base_dir: str = VOICE_PROFILES_DIR):
        self._dir = base_dir
        os.makedirs(self._dir, exist_ok=True)

    @staticmethod
    def _validate_name(name: str) -> str:
        """이름이 파일명으로 쓰이므로 경로 조작 문자를 차단."""
        name = name.strip()
        if not name or any(ch in name for ch in ("/", "\\", "..", "\x00")):
            raise ValueError(f"사용할 수 없는 이름: {name!a}")
        return name

    def _path(self, name: str) -> str:
        return os.path.join(self._dir, f"{name}.npy")

    def register(self, name: str, embedding: np.ndarray) -> str:
        """프로필 등록(같은 이름이면 덮어씀 = 재등록). 확정된 이름을 반환."""
        name = self._validate_name(name)
        np.save(self._path(name), embedding)
        logger.info(f"👤 전역 목소리 프로필 등록: {name}")
        return name

    def list_names(self) -> list[str]:
        return sorted(
            os.path.splitext(f)[0]
            for f in os.listdir(self._dir)
            if f.endswith(".npy")
        )

    def load(self, names: list[str]) -> dict[str, np.ndarray]:
        """요청한 이름들 중 등록돼 있는 것만 {이름: 임베딩}으로 반환."""
        profiles = {}
        for raw_name in names:
            try:
                name = self._validate_name(raw_name)
            except ValueError:
                continue
            path = self._path(name)
            if os.path.isfile(path):
                profiles[name] = np.load(path)
        return profiles

    def delete(self, name: str) -> bool:
        name = self._validate_name(name)
        path = self._path(name)
        if not os.path.isfile(path):
            return False
        os.remove(path)
        logger.info(f"🗑️ 전역 목소리 프로필 삭제: {name}")
        return True

    def rename(self, old_name: str, new_name: str) -> bool:
        old_name = self._validate_name(old_name)
        new_name = self._validate_name(new_name)
        old_path = self._path(old_name)
        if not os.path.isfile(old_path):
            return False
        new_path = self._path(new_name)
        if os.path.isfile(new_path):
            # 다른 사람의 기존 프로필을 조용히 덮어쓰는 사고 방지
            raise ValueError(f"'{new_name}'은(는) 이미 등록된 이름이라 사용할 수 없음")
        os.replace(old_path, new_path)
        logger.info(f"✏️ 전역 목소리 프로필 이름 수정: {old_name} → {new_name}")
        return True
