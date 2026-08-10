import { Contradiction } from "../services/contradiction";
import { DocumentIcon } from "./icons";
import { parseDisplayMessage, parseDecisionMessage } from "../lib/parseContradictionMessage";

type ContradictionDisplayFields = Pick<
  Contradiction,
  | "display_message"
  | "reference_source_name"
  | "reference_type"
  | "reference_file_id"
  | "reference_decision_id"
  | "statement_text_snapshot"
  | "reference_text_snapshot"
>;

interface ContradictionMessageProps {
  contradiction: ContradictionDisplayFields;
  expanded: boolean;
  t: any;
  // 문서/코드 참조(reference_type !== "decision")일 때만 쓰인다 - reference_file_id로 미리보기를 연다.
  onViewReference?: (fileId: string, name: string) => void;
  // 결정 참조(reference_type === "decision")일 때만 쓰인다 - reference_decision_id로 대시보드의
  // 결정사항 이력으로 이동한다. 문서 미리보기와 대상이 완전히 달라서 별도 콜백으로 분리했다.
  onViewDecision?: (decisionId: string, name: string) => void;
}

function ReferenceBadge({ name, onClick }: { name: string; onClick?: () => void }) {
  const className =
    "mt-1.5 inline-flex items-center gap-1 rounded-md border border-recall-border bg-recall-bgMain px-1.5 py-1 text-xs font-medium text-recall-textMuted";

  if (!onClick) {
    return (
      <span className={className}>
        <DocumentIcon size={12} className="flex-shrink-0" />
        {name}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={`${className} text-recall-accent hover:border-recall-accent/50 hover:bg-recall-accent/5`}
    >
      <DocumentIcon size={12} className="flex-shrink-0" />
      {name}
    </button>
  );
}

function renderReferenceBadge(
  c: ContradictionDisplayFields,
  onViewReference?: (fileId: string, name: string) => void,
  onViewDecision?: (decisionId: string, name: string) => void
) {
  if (!c.reference_source_name) return null;

  const onClick =
    c.reference_type === "decision"
      ? c.reference_decision_id && onViewDecision
        ? () => onViewDecision(c.reference_decision_id!, c.reference_source_name!)
        : undefined
      : onViewReference
        ? () => onViewReference(c.reference_file_id, c.reference_source_name!)
        : undefined;

  return <ReferenceBadge name={c.reference_source_name} onClick={onClick} />;
}

export default function ContradictionMessage({
  contradiction: c,
  expanded,
  t,
  onViewReference,
  onViewDecision,
}: ContradictionMessageProps) {
  const parsed = c.display_message ? parseDisplayMessage(c.display_message) : null;
  const decisionParsed = c.display_message && !parsed ? parseDecisionMessage(c.display_message) : null;

  if (decisionParsed) {
    return (
      <div className="mb-2">
        <p className="mb-1.5 text-sm font-semibold leading-snug text-recall-text">{decisionParsed.headline}</p>
        <div className="mb-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
            {t.contradiction_existing_content}
          </p>
          <p data-clamp className={`text-sm text-recall-textMuted ${expanded ? "" : "line-clamp-1"}`}>
            {decisionParsed.existingContent}
          </p>
        </div>
        <div className="mb-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-recall-danger/80">
            {t.contradiction_new_statement}
          </p>
          <p data-clamp className={`text-base text-recall-text ${expanded ? "" : "line-clamp-2"}`}>
            {decisionParsed.newStatement}
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
            {t.contradiction_reason_label}
          </p>
          <p className="text-sm leading-relaxed text-recall-textMuted">{decisionParsed.reason}</p>
        </div>
        {renderReferenceBadge(c, onViewReference, onViewDecision)}
      </div>
    );
  }

  // display_message가 아무 패턴에도 안 맞을 때만(예전 형식 등) 원문을 통째로 보여준다
  if (c.display_message && !parsed) {
    return (
      <div className="mb-2">
        <p data-clamp className={`text-base text-recall-text ${expanded ? "" : "line-clamp-3"}`}>{c.display_message}</p>
        {renderReferenceBadge(c, onViewReference, onViewDecision)}
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
        {renderReferenceBadge(c, onViewReference, onViewDecision)}
      </div>
    </>
  );
}
