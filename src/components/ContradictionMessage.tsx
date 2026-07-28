import { Contradiction } from "../services/contradiction";
import { DocumentIcon } from "./icons";

type ContradictionDisplayFields = Pick<
  Contradiction,
  "display_message" | "reference_source_name" | "statement_text_snapshot" | "reference_text_snapshot"
>;

// display_message는 백엔드가 "'{새 발언}'라고 하셨는데, 기존 자료({문서명})의 '{기존 내용}'와
// 다릅니다." 형태의 문장 하나로 만들어서 내려준다. 그대로 보여주면 새 발언/기존 내용 구분이
// 안 되는 긴 문장 덩어리라 읽기 어려우므로, 패턴을 파싱해서 statement/reference 스냅샷과
// 동일한 "기존 내용 → 새 발언" 두 블록 레이아웃으로 재구성한다. 패턴이 안 맞으면(예전 형식이나
// 문구가 바뀐 경우) display_message 원문을 그대로 보여주는 것으로 안전하게 대체한다.
const DISPLAY_MESSAGE_PATTERN = /^'([\s\S]+)'라고 하셨는데, 기존 자료\([^)]*\)의 '([\s\S]+)'와 다릅니다\.?$/;

function parseDisplayMessage(message: string): { newStatement: string; existingContent: string } | null {
  const match = message.match(DISPLAY_MESSAGE_PATTERN);
  if (!match) return null;
  return { newStatement: match[1], existingContent: match[2] };
}

export default function ContradictionMessage({
  contradiction: c,
  expanded,
  t,
}: {
  contradiction: ContradictionDisplayFields;
  expanded: boolean;
  t: any;
}) {
  const parsed = c.display_message ? parseDisplayMessage(c.display_message) : null;

  // display_message가 파싱이 안 될 때만(예전 형식 등) 원문을 통째로 보여준다
  if (c.display_message && !parsed) {
    return (
      <div className="mb-2">
        <p data-clamp className={`text-base text-recall-text ${expanded ? "" : "line-clamp-3"}`}>{c.display_message}</p>
        {c.reference_source_name && (
          <span className="mt-1.5 inline-flex items-center gap-1 rounded-md border border-recall-border bg-recall-bgMain px-1.5 py-1 text-xs font-medium text-recall-textMuted">
            <DocumentIcon size={12} className="flex-shrink-0" />
            {c.reference_source_name}
          </span>
        )}
      </div>
    );
  }

  const existingContent = parsed?.existingContent ?? c.reference_text_snapshot;
  const newStatement = parsed?.newStatement ?? c.statement_text_snapshot;

  return (
    <>
      <div className="mb-1.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
          {t.contradiction_existing_content}
        </p>
        <p data-clamp className={`text-sm text-recall-textMuted ${expanded ? "" : "line-clamp-1"}`}>
          {existingContent}
        </p>
      </div>
      <div className="mb-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-recall-danger/80">
          {t.contradiction_new_statement}
        </p>
        <p data-clamp className={`text-base text-recall-text ${expanded ? "" : "line-clamp-2"}`}>
          {newStatement}
        </p>
        {c.reference_source_name && (
          <span className="mt-1.5 inline-flex items-center gap-1 rounded-md border border-recall-border bg-recall-bgMain px-1.5 py-1 text-xs font-medium text-recall-textMuted">
            <DocumentIcon size={12} className="flex-shrink-0" />
            {c.reference_source_name}
          </span>
        )}
      </div>
    </>
  );
}
