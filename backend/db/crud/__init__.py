"""도메인별 CRUD 모듈 모음.

기존 crud.py 를 도메인 단위로 분리:
  auth_crud / workspace_crud / room_crud / file_crud / document_crud
  code_crud / content_chunk_crud / similarity_crud             (LLM/RAG 파트)
  meeting_crud / contradiction_crud / ai_chat_crud              (contradiction·ai_chat은 LLM/RAG 파트)
  notification_crud

사용 예:
    from backend.db.crud import content_chunk_crud
    content_chunk_crud.create_chunk(db, ...)
"""
