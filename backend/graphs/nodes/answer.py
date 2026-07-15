from backend.schemas.agent_schema import AgentState
from backend.services.ollama_service import ollama_service


EMPTY_TASK_VALUES = {"할 일 없음", "없음", "해당 없음", "N/A", "null", "None"}

# 최종 답변 생성 전 빈 task 및 의미 없는 task를 제거
def _clean_tasks_for_answer(tasks: list) -> list:
    if not tasks:
        return []

    cleaned_tasks = []

    for task in tasks:
        if not isinstance(task, dict):
            continue

        task_title = (
            task.get("task")
            or task.get("title")
            or task.get("content")
            or ""
        )
        task_title = str(task_title).strip()

        if not task_title or task_title in EMPTY_TASK_VALUES:
            continue

        cleaned_tasks.append({
            **task,
            "task": task_title,
            "status": task.get("status") or "todo",
            "priority": task.get("priority") or "medium",
        })

    return cleaned_tasks


# 추출된 tasks를 최종 답변 문자열로 변환
def _build_task_answer(tasks: list, question_type: str) -> str:
    task_lines = []

    for idx, task in enumerate(tasks, start=1):
        task_title = task.get("task")
        assignee = task.get("assignee") or "담당자 미정"
        deadline = task.get("deadline") or "마감일 미정"

        task_lines.append(
            f"{idx}. {task_title}\n"
            f"   - 담당자: {assignee}\n"
            f"   - 마감일: {deadline}"
        )

    if question_type == "task_from_memory":
        answer_title = "대화에서 추출한 할 일은 다음과 같습니다."
    else:
        answer_title = "문서에서 추출한 할 일은 다음과 같습니다."

    return answer_title + "\n\n" + "\n\n".join(task_lines)


# 최종 답변 생성을 담당하는 LangGraph 노드
def answer_node(state: AgentState) -> AgentState:
    user_message = state.get("user_message", "")
    question_type = state.get("question_type", "general_answer")
    rag_context = state.get("rag_context") or ""
    rag_search_result = state.get("rag_search_result")
    memory_context = state.get("memory_context") or ""
    tasks = _clean_tasks_for_answer(state.get("tasks") or [])


    if state.get("need_rag", False):
        if not rag_context.strip() and not rag_search_result:
            return {
                **state,
                "tasks": tasks,
                "final_answer": "관련 문서 또는 지식 검색 결과를 찾지 못했습니다. 질문 내용을 조금 더 구체적으로 입력해 주세요.",
                "current_step": "answer_node",
                "error": state.get("error"),
            }

    if state.get("need_task_extract", False):
        if tasks:
            return {
                **state,
                "tasks": tasks,
                "final_answer": _build_task_answer(tasks, question_type),
                "current_step": "answer_node",
                "error": state.get("error"),
            }
        return {
            **state,
            "tasks": [],
            "final_answer": "문서 또는 대화 내용에서 추출할 수 있는 할 일을 찾지 못했습니다.",
            "current_step": "answer_node",
            "error": state.get("error"),
        }

    try:
        final_answer = ollama_service.generate_answer_for_graph(
            user_message=user_message,
            question_type=question_type,
            rag_context=rag_context,
            rag_search_result=rag_search_result,
            memory_context=memory_context,
            tasks=tasks,
        )

        return {
            **state,
            "tasks": tasks,
            "final_answer": final_answer,
            "current_step": "answer_node",
            "error": state.get("error"),
        }

    except Exception as e:
        return {
            **state,
            "tasks": tasks,
            "final_answer": "답변 생성 중 오류가 발생했습니다.",
            "current_step": "answer_node",
            "error": str(e),
        }