// 회원가입 때 고를 수 있는 프로필 색상 팔레트. 안 고르면 이 중 하나를 랜덤 배정
export const AVATAR_COLORS = [
  "#f87171", // red
  "#fb7185", // rose
  "#f472b6", // pink
  "#e879f9", // fuchsia
  "#c084fc", // purple
  "#a78bfa", // violet
  "#818cf8", // indigo
  "#60a5fa", // blue
  "#38bdf8", // sky
  "#22d3ee", // cyan
  "#2dd4bf", // teal
  "#4ade80", // green
  "#a3e635", // lime
  "#facc15", // yellow
  "#fbbf24", // amber
  "#fb923c", // orange
  "#f97316", // orange-dark
  "#94a3b8", // slate
  "#78716c", // stone
  "#34d399", // emerald
  "#fda4af", // light rose
  "#93c5fd", // light blue
  "#fcd34d", // light amber
  "#c4b5fd", // light violet
];

export function randomAvatarColor(): string {
  return AVATAR_COLORS[Math.floor(Math.random() * AVATAR_COLORS.length)];
}

// username 기반으로 항상 같은 색이 나오도록 하는 결정적(deterministic) 배정
export function hashAvatarColor(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash << 5) - hash + key.charCodeAt(i);
    hash |= 0;
  }
  const index = Math.abs(hash) % AVATAR_COLORS.length;
  return AVATAR_COLORS[index];
}

// 백엔드에 avatarColor 저장 필드가 없어 프론트(localStorage)에서 계정별로 고정 저장
function storageKey(username: string): string {
  return `avatar_color:${username}`;
}

export function loadAvatarColor(username: string): string | null {
  return localStorage.getItem(storageKey(username));
}

export function saveAvatarColor(username: string, color: string): void {
  localStorage.setItem(storageKey(username), color);
}