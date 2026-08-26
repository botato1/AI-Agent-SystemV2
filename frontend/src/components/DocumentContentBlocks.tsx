// PDF에서 뽑은 원문은 문단 중간에도 줄마다 강제 줄바꿈이 들어가 있는 경우가 많아서
// (실제 OCR 오류가 아니라 추출 방식 특성), 진짜 문단 구분(빈 줄)과 번호/기호로 시작하는
// 목록 항목의 줄바꿈만 남기고 나머지 줄바꿈은 공백으로 합쳐서 읽기 편하게 만든다.
const LIST_ITEM_PATTERN = /^\s*(\d+[.)]|[-•*])\s+/;

export function cleanExtractedText(text: string): string {
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

export default function ContentBlocks({ text }: { text: string }) {
  const blocks = splitIntoBlocks(text);

  return (
    <>
      {blocks.map((block, blockIndex) => {
        if (block.type === "table") {
          const rows = block.lines.filter((l) => l.trim() && !isSeparatorRow(l)).map(parseTableRow);
          if (rows.length === 0) return null;

          return (
            <div key={blockIndex} className="overflow-x-auto rounded-lg border border-recall-border">
              <table className="border-collapse text-sm">
                <tbody>
                  {rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className={rowIndex === 0 ? "bg-recall-bgMain" : ""}>
                      {row.map((cell, cellIndex) => (
                        <td
                          key={cellIndex}
                          className={`whitespace-nowrap border border-recall-border px-2 py-1.5 text-recall-textMuted ${
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
