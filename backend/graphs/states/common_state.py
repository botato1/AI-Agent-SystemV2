# backend/graphs/states/common_state.py

# 모든 Re:Call LangGraph 상태에서 공통으로 사용하는 기본 상태
# workspace_id와 category_id는 그래프 실행 전에 확정
from typing import NotRequired, Required, TypedDict


class CommonState(TypedDict, total=False):
    # 데이터 격리 및 검색 범위
    workspace_id: Required[str]
    category_id: Required[str]

    # 현재 실행 중인 노드 이름
    current_step: NotRequired[str]

    # 노드 실행 중 발생한 오류 메시지
    error: NotRequired[str]