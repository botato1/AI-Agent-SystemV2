# backend/services/ollama_service.py
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from backend.modules.llm.ollama_client import (
    normalize_query,
    classify_intent,
    generate_answer_for_graph as client_generate_answer_for_graph,
    extract_tasks_from_content as client_extract_tasks_from_content,
)
from backend.services.rag_service import rag_service


class OllamaService:
    """
    LangGraph node에서 재사용할 LLM/RAG 보조 함수 모음.

    의도분류 체계:
    - task_from_rag     : RAG 자료(회의록/문서) 기반 할일 추출
    - task_from_memory  : 채팅 기록 기반 할일 추출
    - knowledge_search  : RAG 자료로 답변 생성
    - summary_from_rag  : RAG 자료 기반 요약
    - general_answer    : RAG/memory 둘 다 불필요
    """

    @staticmethod
    def normalize_text(value: str | None) -> str:
        if not value:
            return ""
        return unicodedata.normalize("NFC", value).strip()

    @staticmethod
    def normalize_user_input(user_input: str) -> str:
        normalized = normalize_query(user_input)
        return OllamaService.normalize_text(normalized)

    @staticmethod
    def extract_filename(query: str) -> str | None:
        query = OllamaService.normalize_text(query)
        pattern = r"([가-힣a-zA-Z0-9_\-\s]+?\.(?:pdf|docx|doc|md|xlsx|txt|pptx|csv))"
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return OllamaService.normalize_text(match.group(1))
        return None

    # ── 키워드 보정 ─────────────────────────────────────────

    @staticmethod
    def is_memory_source_request(message: str) -> bool:
        memory_keywords = [
            "방금 답변", "방금 내용", "이전 답변", "이전 내용",
            "아까 답변", "아까 내용", "위 내용", "이 내용",
            "그 내용", "방금", "아까", "이전에", "전에 말한",
            "대화에서", "우리가 얘기한", "채팅에서", "나눈 얘기",
        ]
        return any(keyword in message for keyword in memory_keywords)

    @staticmethod
    def is_task_request(message: str) -> bool:
        task_keywords = [
            "할 일", "해야 할 일", "업무", "태스크", "task",
            "담당자", "마감일", "액션아이템", "액션 아이템",
        ]
        return any(keyword in message for keyword in task_keywords)

    # ── 의도 → AgentState 플래그 매핑 ─────────────────────────

    @staticmethod
    def map_intent_to_agent_flags(intent: str) -> dict[str, Any]:
        result = {
            "question_type": "general_answer",
            "need_general_answer": True,
            "need_memory": False,
            "need_rag": False,
            "need_task_extract": False,
        }

        if intent == "task_from_rag":
            result["question_type"] = "task_from_rag"
            result["need_rag"] = True
            result["need_task_extract"] = True

        elif intent == "task_from_memory":
            result["question_type"] = "task_from_memory"
            result["need_memory"] = True
            result["need_task_extract"] = True

        elif intent == "knowledge_search":
            result["question_type"] = "knowledge_search"
            result["need_rag"] = True

        elif intent == "summary_from_rag":
            result["question_type"] = "summary_from_rag"
            result["need_rag"] = True

        else:
            result["question_type"] = "general_answer"

        result["need_general_answer"] = not (
            result["need_memory"]
            or result["need_rag"]
            or result["need_task_extract"]
        )

        return result

    # ── LangGraph classifier_node에서 사용할 의도 분류 함수 ──

    @staticmethod
    def classify_for_graph(user_input: str) -> dict[str, Any]:
        normalized = OllamaService.normalize_user_input(user_input)

        try:
            intent_result = classify_intent(normalized)
            intent = intent_result.get("intent", "general_answer")
        except Exception as e:
            print(f"[OllamaService classify_for_graph 에러]: {str(e)}")
            intent = "general_answer"

        # v1에서 남아있는 notion_save intent가 들어오더라도
        # v2에서는 지원하지 않으므로 general_answer로 보정
        if intent == "notion_save":
            intent = "general_answer"

        mapped = OllamaService.map_intent_to_agent_flags(intent)

        target_filename = OllamaService.extract_filename(normalized)

        # 키워드 보정: LLM이 놓친 경우만 보강
        if OllamaService.is_task_request(normalized) and not mapped["need_task_extract"]:
            if OllamaService.is_memory_source_request(normalized):
                mapped["question_type"] = "task_from_memory"
                mapped["need_memory"] = True
                mapped["need_task_extract"] = True
                mapped["need_rag"] = False
            else:
                mapped["question_type"] = "task_from_rag"
                mapped["need_rag"] = True
                mapped["need_task_extract"] = True

        mapped["need_general_answer"] = not (
            mapped["need_memory"]
            or mapped["need_rag"]
            or mapped["need_task_extract"]
        )

        return {
            "question_type": mapped["question_type"],
            "intent": intent,
            "normalized_input": normalized,
            "need_general_answer": mapped["need_general_answer"],
            "need_memory": mapped["need_memory"],
            "need_rag": mapped["need_rag"],
            "need_task_extract": mapped["need_task_extract"],
            "target_filename": target_filename,
        }

    # ── RAG 검색 filter 생성 ────────────────────────────────

    @staticmethod
    def build_rag_filter(
        target_document_id: str | None = None,
        target_filename: str | None = None,
        existing_filter: dict | None = None,
    ) -> dict | None:
        if existing_filter:
            return existing_filter
        if target_document_id:
            return {"document_id": target_document_id}
        if target_filename:
            return {"filename": OllamaService.normalize_text(target_filename)}
        return None

    @staticmethod
    def deduplicate_docs(docs: list[dict]) -> list[dict]:
        seen = set()
        unique_docs = []

        for doc in docs:
            title = OllamaService.normalize_text(doc.get("title"))
            content = (doc.get("content") or "").strip()
            dedupe_key = (title, content)

            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            unique_docs.append(doc)

        return unique_docs

    @staticmethod
    def format_sources(docs: list[dict]) -> list[dict]:
        sources = []
        seen = set()

        for doc in docs:
            title = doc.get("title")
            source = doc.get("source") or doc.get("filename") or title

            dedupe_key = (
                OllamaService.normalize_text(title),
                OllamaService.normalize_text(source),
            )

            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)

            sources.append({
                "id": doc.get("id") or doc.get("document_id") or doc.get("chroma_id"),
                "title": title,
                "source": source,
                "source_url": doc.get("source_url"),
                "data_type": doc.get("data_type"),
                "score": doc.get("score"),
                "importance": doc.get("importance") or doc.get("importance_score"),
                "created_at": doc.get("created_at"),
                "tags": doc.get("tags"),
            })

        return sources

    @staticmethod
    def filename_in_title(target_filename: str | None, title: str | None) -> bool:
        normalized_filename = OllamaService.normalize_text(target_filename)
        normalized_title = OllamaService.normalize_text(title)

        if not normalized_filename or not normalized_title:
            return False

        return normalized_filename in normalized_title

    # ── Graph 답변 생성 ─────────────────────────────────────

    @staticmethod
    def generate_answer_for_graph(
        user_message: str,
        question_type: str = "general_answer",
        rag_context: str | None = None,
        rag_search_result: dict | None = None,
        memory_context: str | None = None,
        tasks: list | None = None,
    ) -> str:
        safe_rag_context = rag_context or ""
        safe_memory_context = memory_context or ""

        # 특정 문서 직접 조회용 context 길이 제한
        if len(safe_rag_context) > 12000:
            safe_rag_context = safe_rag_context[:12000]

        # 대화 기록도 너무 길어질 수 있으므로 제한
        if len(safe_memory_context) > 8000:
            safe_memory_context = safe_memory_context[:8000]

        return client_generate_answer_for_graph(
            user_message=user_message,
            question_type=question_type,
            rag_context=safe_rag_context,
            rag_search_result=rag_search_result,
            memory_context=safe_memory_context,
            tasks=tasks or [],
        )

    @staticmethod
    def extract_tasks_from_content(content: str) -> list[dict]:
        return client_extract_tasks_from_content(content)

    # ── 단일 파이프라인 테스트용 함수 ────────────────────────

    @staticmethod
    def process_query(user_input: str, conversation_id: str = None) -> dict:
        try:
            classified = OllamaService.classify_for_graph(user_input)

            rag_context = ""
            sources = []
            rag_search_result = None

            if classified.get("need_rag"):
                rag_filter = OllamaService.build_rag_filter(
                    target_filename=classified.get("target_filename")
                )

                rag_search_result = rag_service.retrieve_relevant_knowledge_sync(
                    query=classified.get("normalized_input") or user_input,
                    top_k=5,
                    filter=rag_filter,
                    question_type=classified.get("question_type", "general_answer"),
                )

                if rag_search_result and rag_search_result.get("count", 0) > 0:
                    docs = OllamaService.deduplicate_docs(
                        rag_search_result.get("data", [])
                    )
                    rag_context = "\n\n".join(
                        [doc.get("content", "") for doc in docs if doc.get("content")]
                    )
                    sources = OllamaService.format_sources(docs)

            answer = OllamaService.generate_answer_for_graph(
                user_message=user_input,
                question_type=classified.get("question_type", "general_answer"),
                rag_context=rag_context,
                rag_search_result=rag_search_result,
            )

            return {
                "status": "success",
                "original_input": user_input,
                "normalized_input": classified.get("normalized_input"),
                "question_type": classified.get("question_type"),
                "intent": classified.get("intent"),
                "need_rag": classified.get("need_rag"),
                "answer": answer,
                "sources": sources,
                "error": None,
            }

        except Exception as e:
            print(f"[OllamaService 에러]: {str(e)}")
            return {
                "status": "error",
                "original_input": user_input,
                "normalized_input": user_input,
                "question_type": "general_answer",
                "intent": "general_answer",
                "need_rag": False,
                "answer": "처리 중 오류가 발생했습니다.",
                "sources": [],
                "error": str(e),
            }


ollama_service = OllamaService()