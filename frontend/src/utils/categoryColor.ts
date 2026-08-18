// 카테고리별로 순서대로 배정하는 고정 팔레트 - 라이트/다크 배경 양쪽에서 무난하게 보이는 mid-tone hex.
// 완전 랜덤이 아니라 display_order 기준 인덱스로 순환 배정해서, 카테고리가 늘어나도 예측 가능하게 겹친다.
const CATEGORY_COLOR_PALETTE = [
  "#7F77DD", // purple
  "#1D9E75", // teal
  "#D85A30", // coral
  "#D4537E", // pink
  "#378ADD", // blue
  "#639922", // green
  "#BA7517", // amber
  "#888780", // gray
];

export function getCategoryColor(index: number): string {
  return CATEGORY_COLOR_PALETTE[index % CATEGORY_COLOR_PALETTE.length];
}
