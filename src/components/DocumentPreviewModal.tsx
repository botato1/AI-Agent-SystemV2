import { useEffect, useState } from "react";
import { DocumentDetail, getDocumentApi } from "../services/document";
import { CloseIcon, DocumentIcon } from "./icons";

// PDF에서 뽑은 원문은 문단 중간에도 줄마다 강제 줄바꿈이 들어가 있는 경우가 많아서
// (실제 OCR 오류가 아니라 추출 방식 특성), 진짜 문단 구분(빈 줄)과 번호/기호로 시작하는
// 목록 항목의 줄바꿈만 남기고 나머지 줄바꿈은 공백으로 합쳐서 읽기 편하게 만든다.
const LIST_ITEM_PATTERN = /^\s*(\d+[.)]|[-•*])\s+/;

function cleanExtractedText(text: string): string {
  // 일반 공백과 절대 겹치지 않는 마커로 "진짜 문단 구분(빈 줄)"만 표시해뒀다가 마지막에 복원한다.
  const PARAGRAPH_MARKER = String.fromCharCode(0);

  const paragraphProtected = text.replace(/\r\n/g, "\n").replace(/\n{2,}/g, PARAGRAPH_MARKER);

  const lines = paragraphProtected.split("\n");
  let merged = lines[0] || "";
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    merged += LIST_ITEM_PATTERN.test(line) ? "\n" + line : " " + line;
  }

  return merged
    .split(PARAGRAPH_MARKER)
    .join("\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

// --- 표(파이프 "|" 구분) 감지 및 렌더링 ---

interface TextBlock {
  type: "table" | "prose";
  lines: string[];
}

function isTableRow(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return false;
  return (trimmed.match(/\|/g) || []).length >= 2;
}

// 마크다운 표의 "---|---|---" 구분선 행은 화면에 그대로 보여줄 필요 없음
function isSeparatorRow(line: string): boolean {
  const trimmed = line.trim();
  return /^[|\s:-]+$/.test(trimmed) && trimmed.includes("-");
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function splitIntoBlocks(text: string): TextBlock[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: TextBlock[] = [];
  let current: TextBlock | null = null;

  for (const line of lines) {
    const type: TextBlock["type"] = isTableRow(line) ? "table" : "prose";
    if (!current || current.type !== type) {
      current = { type, lines: [] };
      blocks.push(current);
    }
    current.lines.push(line);
  }

  return blocks;
}

function ContentBlocks({ text }: { text: string }) {
  const blocks = splitIntoBlocks(text);

  return (
    <>
      {blocks.map((block, blockIndex) => {
        if (block.type === "table") {
          const rows = block.lines.filter((l) => l.trim() && !isSeparatorRow(l)).map(parseTableRow);
          if (rows.length === 0) return null;

          return (
            <div key={blockIndex} className="overflow-x-auto rounded-lg border border-recall-border">
              <table className="w-full border-collapse text-sm">
                <tbody>
                  {rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className={rowIndex === 0 ? "bg-recall-bgMain" : ""}>
                      {row.map((cell, cellIndex) => (
                        <td
                          key={cellIndex}
                          className={`border border-recall-border px-2 py-1.5 text-recall-textMuted ${
                            rowIndex === 0 ? "font-semibold text-recall-text" : ""
                          }`}
                        >
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        const cleaned = cleanExtractedText(block.lines.join("\n"));
        if (!cleaned) return null;

        return (
          <p key={blockIndex} className="whitespace-pre-wrap text-sm leading-relaxed text-recall-textMuted">
            {cleaned}
          </p>
        );
      })}
    </>
  );
}

interface DocumentPreviewModalProps {
  workspaceId: string;
  documentId: string;
  documentName: string;
  onClose: () => void;
}

export default function DocumentPreviewModal({
  workspaceId,
  documentId,
  documentName,
  onClose,
}: DocumentPreviewModalProps) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      const res = await getDocumentApi(workspaceId, documentId);
      if (!cancelled) {
        setDetail(res.status === "success" ? res.document : null);
        setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, documentId]);

  const sortedChunks = detail?.raw.chunks ? [...detail.raw.chunks].sort((a, b) => a.chunk_index - b.chunk_index) : [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between border-b border-recall-border pb-3">
          <div className="flex min-w-0 items-center gap-2">
            <DocumentIcon size={16} className="flex-shrink-0 text-recall-accent" />
            <p className="truncate text-base font-semibold">{documentName}</p>
          </div>
          <button onClick={onClose} className="flex-shrink-0 text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        {isLoading ? (
          <p className="text-base text-recall-textMuted">불러오는 중...</p>
        ) : !detail ? (
          <p className="text-base text-recall-danger">문서를 불러오지 못했습니다.</p>
        ) : detail.analysis_status !== "completed" ? (
          <p className="text-base text-recall-textMuted">
            {detail.analysis_status === "failed" ? "문서 분석에 실패했습니다." : "아직 분석이 완료되지 않았습니다."}
          </p>
        ) : (
          <div className="flex-1 space-y-4 overflow-y-auto">
            {detail.analysis.summary && (
              <div>
                <p className="mb-1.5 text-sm font-semibold uppercase tracking-wide text-recall-textMuted">요약</p>
                <p className="whitespace-pre-wrap text-base leading-relaxed text-recall-text">
                  {detail.analysis.summary}
                </p>
              </div>
            )}

            {(detail.analysis.table_count || detail.analysis.graph_count) ? (
              <div className="flex flex-wrap gap-1.5 text-xs text-recall-textMuted">
                {!!detail.analysis.table_count && (
                  <span className="rounded-full border border-recall-border bg-recall-bgMain px-2 py-0.5">
                    표 {detail.analysis.table_count}개
                  </span>
                )}
                {!!detail.analysis.graph_count && (
                  <span className="rounded-full border border-recall-border bg-recall-bgMain px-2 py-0.5">
                    차트/그래프 {detail.analysis.graph_count}개 (원본 이미지는 미리보기 미지원)
                  </span>
                )}
              </div>
            ) : null}

            {sortedChunks.length > 0 ? (
              <div>
                <p className="mb-1.5 text-sm font-semibold uppercase tracking-wide text-recall-textMuted">원문</p>
                <div className="space-y-3">
                  {sortedChunks.map((chunk, i) => {
                    const showPageLabel =
                      chunk.page_number != null &&
                      (i === 0 || sortedChunks[i - 1].page_number !== chunk.page_number);
                    return (
                      <div key={chunk.chunk_index} className="space-y-2">
                        {showPageLabel && (
                          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-recall-textMuted/70">
                            {chunk.page_number}페이지
                          </p>
                        )}
                        <ContentBlocks text={chunk.content} />
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : detail.raw.original_text ? (
              <div>
                <p className="mb-1.5 text-sm font-semibold uppercase tracking-wide text-recall-textMuted">원문</p>
                <div className="space-y-2">
                  <ContentBlocks text={detail.raw.original_text} />
                </div>
              </div>
            ) : null}

            {!detail.analysis.summary && sortedChunks.length === 0 && !detail.raw.original_text && (
              <p className="text-base text-recall-textMuted">표시할 내용이 없습니다.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
