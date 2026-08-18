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
