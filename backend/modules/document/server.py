"""FastAPI 서버 — PDF 업로드 → 문서처리 파이프라인 → JSON 반환"""
from __future__ import annotations

import os
import glob
import json
import os
import site
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# paddlepaddle-gpu nvidia CUDA DLL 경로 등록 (Windows)
if os.name == "nt":
    for _sp in site.getsitepackages():
        for _d in glob.glob(os.path.join(_sp, "nvidia", "*", "bin")):
            os.add_dll_directory(_d)

# 저장 경로 (repo 루트 기준)
_REPO_ROOT     = Path(__file__).parent.parent.parent.parent  # AI-Agent-System/
_STORAGE_DIR   = _REPO_ROOT / "storage" / "uploads" / "documents"
_DATA_DIR      = _REPO_ROOT / "data" / "uploads" / "documents"

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from doc_processor.core.pipeline import DocumentPipeline
from doc_processor.output.assembler import assemble

app = FastAPI(title="Document Processor API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 파이프라인 싱글톤 (서버 시작 시 1회 로드)
_pipeline: DocumentPipeline | None = None


def get_pipeline() -> DocumentPipeline:
    global _pipeline
    if _pipeline is None:
        print("[Server] 파이프라인 초기화 중...")
        _pipeline = DocumentPipeline()
        print("[Server] 파이프라인 준비 완료")
    return _pipeline


@app.on_event("startup")
async def startup():
    get_pipeline()


@app.get("/health")
def health():
    """서버 상태 확인"""
    return {"status": "ok"}


@app.delete("/api/document/{document_id}")
async def delete_document(document_id: str):
    """
    문서 ID로 원본 파일과 처리 결과 JSON을 삭제합니다.

    - **document_id**: 8003 서버에서 관리하는 문서 ID
    """
    deleted_file = False
    deleted_json = False
    error_msg = None

    # 저장 디렉토리 확인
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    # document_id로 JSON 파일 찾기
    json_file_path = None
    pdf_file_path = None

    # JSON 파일 순회해서 document_id 찾기
    for json_file in _DATA_DIR.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("document_id") == document_id:
                    json_file_path = json_file
                    # 같은 이름의 PDF 파일 찾기
                    stem = json_file.stem
                    for ext in [".pdf", ".docx", ".doc", ".txt"]:
                        potential_pdf = _STORAGE_DIR / f"{stem}{ext}"
                        if potential_pdf.exists():
                            pdf_file_path = potential_pdf
                            break
                    break
        except Exception:
            continue

    # PDF 파일 삭제
    if pdf_file_path and pdf_file_path.exists():
        try:
            pdf_file_path.unlink()
            deleted_file = True
        except Exception as e:
            error_msg = f"PDF 파일 삭제 실패: {str(e)}"

    # JSON 파일 삭제
    if json_file_path and json_file_path.exists():
        try:
            json_file_path.unlink()
            deleted_json = True
        except Exception as e:
            error_msg = f"JSON 파일 삭제 실패: {str(e)}"

    # 응답 구성
    if deleted_file or deleted_json:
        status = "success" if (deleted_file and deleted_json) else "partial_success"
        message = "문서 원본 파일과 처리 결과 JSON이 삭제되었습니다." if (deleted_file and deleted_json) else "일부 파일만 삭제되었습니다."
    else:
        status = "error"
        message = "삭제할 문서를 찾을 수 없습니다."
        error_msg = "document_not_found"

    return JSONResponse(
        content={
            "status": status,
            "message": message,
            "document_id": document_id,
            "deleted": {
                "file": deleted_file,
                "json": deleted_json
            },
            "error": error_msg
        },
        status_code=200 if status in ("success", "partial_success") else 404
    )


@app.post("/api/document")
async def process_pdf(
    file: UploadFile = File(...),
    room_id: str = Form(default=""),
    type: str = Form("document"),
):
    """
    PDF 파일을 업로드하면 문서처리 결과를 JSON으로 반환합니다.

    - **file**: PDF 파일
    - **room_id**: 채팅방 ID
    - **type**: 문서 타입 (document / meeting / voice)
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    try:
        # 원본 PDF 저장
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(file.filename).stem
        suffix = Path(file.filename).suffix
        saved_pdf = _STORAGE_DIR / file.filename
        if saved_pdf.exists():
            saved_pdf = _STORAGE_DIR / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
        saved_pdf.write_bytes(await file.read())

        start = time.time()
        pipeline = get_pipeline()

        doc_result = pipeline.run(str(saved_pdf))
        assembled  = assemble(doc_result)
        elapsed    = round(time.time() - start, 2)

        out = assembled.model_dump(mode="json") if hasattr(assembled, "model_dump") else assembled.__dict__

        # 처리 시간 추가
        if isinstance(out.get("metadata"), dict):
            out["metadata"]["api_processing_time_sec"] = elapsed

        # 팀 공통 스키마 필드 추가
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        out.setdefault("type", "document")
        out.setdefault("summary", out.get("content", "")[:200] if out.get("content") else "")
        out.setdefault("language", "ko")
        out.setdefault("created_at", now)
        out.setdefault("importance_score", 0)
        out.setdefault("related_documents", [])
        out.setdefault("notion_url", None)
        out.setdefault("chroma_id", None)
        out.setdefault("error", None)
        out.setdefault("user_edited", False)

        # 프론트 채팅 연동용 + 8000 메타데이터 저장용
        out["document_id"] = out.get("id")
        out["filename"]    = file.filename
        out["file_path"]   = str(saved_pdf)
        out["room_id"]     = room_id
        out["type"]        = type

        # 추출 JSON 저장
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        json_filename = saved_pdf.stem + ".json"
        saved_json    = _DATA_DIR / json_filename
        saved_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

        out["json_path"] = str(saved_json)

        return JSONResponse(content=out)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8003, reload=False)
