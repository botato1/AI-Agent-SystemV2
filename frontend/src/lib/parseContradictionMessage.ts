// display_message는 백엔드가 "'{새 발언}'라고 하셨는데, 기존 자료({문서명})의 '{기존 내용}'와
// 다릅니다." 형태의 문장 하나로 만들어서 내려준다. 그대로 보여주면 새 발언/기존 내용 구분이
// 안 되는 긴 문장 덩어리라 읽기 어려우므로, 패턴을 파싱해서 두 블록으로 재구성한다. 패턴이 안
// 맞으면(예전 형식이나 문구가 바뀐 경우) null을 돌려줘서 호출한 쪽이 원문을 그대로 보여주게 한다.
const DISPLAY_MESSAGE_PATTERN = /^'([\s\S]+)'라고 하셨는데, 기존 자료\([^)]*\)의 '([\s\S]+)'와 다릅니다\.?$/;

export function parseDisplayMessage(message: string): { newStatement: string; existingContent: string } | null {
  const match = message.match(DISPLAY_MESSAGE_PATTERN);
  if (!match) return null;
  return { newStatement: match[1], existingContent: match[2] };
}

// 결정 변경(judgment_case) 쪽 display_message는 "{판단 문구}: '{새 내용}' (기존: '{기존 내용}',
// 사유: {사유})." 형태의 다른 패턴이라 위 패턴과는 별도로 파싱한다.
const DECISION_MESSAGE_PATTERN = /^(.+?):\s*'([\s\S]+?)'\s*\(기존:\s*'([\s\S]+?)',\s*사유:\s*([\s\S]+?)\)\.?$/;

export function parseDecisionMessage(
  message: string
): { headline: string; newStatement: string; existingContent: string; reason: string } | null {
  const match = message.match(DECISION_MESSAGE_PATTERN);
  if (!match) return null;
  return { headline: match[1].trim(), newStatement: match[2], existingContent: match[3], reason: match[4].trim() };
}

// "반영" 확인 팝업에 실제 기존/변경 내용을 보여주기 위해, ContradictionMessage가 화면에
// 표시할 때 쓰는 것과 같은 파싱 우선순위(파싱된 문구 > 스냅샷 원문)로 뽑아낸다.
export function getContradictionPreviewContent(c: {
  display_message?: string | null;
  statement_text_snapshot: string;
  reference_text_snapshot: string;
}): { existingContent: string; newStatement: string } {
  const parsed = c.display_message ? parseDisplayMessage(c.display_message) : null;
  const decisionParsed = c.display_message && !parsed ? parseDecisionMessage(c.display_message) : null;

  if (decisionParsed) {
    return { existingContent: decisionParsed.existingContent, newStatement: decisionParsed.newStatement };
  }
  return {
    existingContent: parsed?.existingContent ?? c.reference_text_snapshot,
    newStatement: parsed?.newStatement ?? c.statement_text_snapshot,
  };
}

function truncateForConfirm(text: string, max = 80): string {
  const trimmed = text.trim();
  return trimmed.length > max ? `${trimmed.slice(0, max)}…` : trimmed;
}

// "반영하면 되돌릴 수 없다"는 확인 팝업이 정작 뭘 반영하는지 안 보여줘서, 내용을 제대로
// 확인하지 못한 채 누르는 사고가 날 수 있었다 - 팝업 문구 안에 기존/변경 내용을 같이 넣는다.
export function buildApplyConfirmMessage(t: any, existingContent: string, newStatement: string): string {
  return [
    `${t.contradiction_existing_content}\n${truncateForConfirm(existingContent)}`,
    `${t.contradiction_new_statement}\n${truncateForConfirm(newStatement)}`,
    t.contradiction_apply_confirm,
  ].join("\n\n");
}
