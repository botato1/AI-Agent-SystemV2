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