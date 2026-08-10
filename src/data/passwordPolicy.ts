// 회원가입/비밀번호 변경 시 공통으로 적용하는 비밀번호 정책.
// 백엔드도 동일 기준으로 검증해서 400을 반환하므로, 프론트에서 먼저 걸러서
// 사용자가 바로 이유를 알 수 있게 한다.
const MIN_LENGTH = 8;
const MAX_LENGTH_BYTES = 72;

// 되돌려주는 값이 null이면 통과, 아니면 사용자에게 보여줄 에러 메시지.
export function validatePassword(password: string): string | null {
  if (password.length < MIN_LENGTH) {
    return `비밀번호는 ${MIN_LENGTH}자 이상이어야 합니다.`;
  }

  const byteLength = new TextEncoder().encode(password).length;
  if (byteLength > MAX_LENGTH_BYTES) {
    return `비밀번호는 ${MAX_LENGTH_BYTES}바이트를 초과할 수 없습니다.`;
  }

  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);
  const kindCount = [hasUpper, hasLower, hasDigit, hasSpecial].filter(Boolean).length;

  if (kindCount < 2) {
    return "영문 대문자, 영문 소문자, 숫자, 특수문자 중 2종류 이상을 조합해 주세요.";
  }

  return null;
}
