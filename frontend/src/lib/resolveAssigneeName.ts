// 회의에서는 보통 "나연님", "승주님"처럼 이름만으로 부르다 보니, 할 일 담당자 입력에도
// 성이 빠진 이름이 그대로 남는 경우가 많다. 워크스페이스 멤버 중 입력값을 부분 문자열로
// 포함하는 사람이 한 명뿐이면, 그 사람의 전체 이름(성 포함)으로 자동 보정해준다.
// 매치가 없거나(오타 등) 여러 명이 걸리면(동명이인) 원래 입력값을 그대로 둔다 - 함부로
// 아무나로 단정 짓지 않기 위함.
export function resolveAssigneeName(input: string, memberList: string[]): string {
  const trimmed = input.trim();
  if (!trimmed) return input;

  const exactMatch = memberList.find((name) => name === trimmed);
  if (exactMatch) return exactMatch;

  const partialMatches = memberList.filter((name) =>
    name.toLowerCase().includes(trimmed.toLowerCase())
  );
  if (partialMatches.length === 1) return partialMatches[0];

  return input;
}
