import { Theme } from "../hooks/useTheme";
import { MoonIcon, SunIcon } from "./icons";

interface SettingsProps {
  onClose: () => void;
  theme: Theme;
  onToggleTheme: () => void;
}

// 리스트형 설정 화면. 프로필/계정 정보는 별도 "내 프로필" 팝업으로 분리했고,
// 여기는 워크스페이스/알림/화면 설정만 다룸 (Ver2 Settings 재설계 패턴 재사용)
const settingsSections = [
  {
    id: "workspace",
    title: "워크스페이스",
    items: [
      { label: "워크스페이스 이름", value: "비트 프로젝트" },
      { label: "팀원 관리", value: "6명" },
      { label: "카테고리 관리", value: "" },
    ],
  },
  {
    id: "notifications",
    title: "알림",
    items: [
      { label: "새 메시지 알림", value: "켜짐" },
      { label: "회의 시작 알림", value: "켜짐" },
      { label: "모순 감지 알림", value: "켜짐" },
    ],
  },
  {
    id: "display",
    title: "화면",
    items: [{ label: "언어", value: "한국어" }],
  },
];

export default function Settings({ onClose, theme, onToggleTheme }: SettingsProps) {
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/50">
      <div className="flex h-[500px] w-[600px] flex-col rounded-xl border border-recall-border bg-recall-bg text-recall-text">
        <div className="flex items-center justify-between border-b border-recall-border px-5 py-4">
          <p className="text-base font-medium">설정</p>
          <button
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-recall-textMuted hover:bg-white/5"
          >
            닫기
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {settingsSections.map((section) => (
            <div key={section.id} className="mb-6">
              <p className="mb-2 text-xs font-medium text-recall-textMuted">{section.title}</p>
              <div className="overflow-hidden rounded-lg border border-recall-border">
                {section.id === "display" && (
                  <button
                    onClick={onToggleTheme}
                    className="flex w-full items-center justify-between border-b border-recall-border px-3 py-2.5 text-sm"
                  >
                    <span className="flex items-center gap-2 text-recall-text">
                      {theme === "dark" ? <MoonIcon size={14} /> : <SunIcon size={14} />}
                      {theme === "dark" ? "다크 모드" : "라이트 모드"}
                    </span>
                    {/* 토글 트랙: span(inline) 대신 div(block)로 둬야 절대위치 자식의 위치 계산이 정상 동작함 */}
                    <div
                      className={`relative h-5 w-9 flex-shrink-0 rounded-full transition-colors ${
                        theme === "dark" ? "bg-recall-accent" : "bg-recall-border"
                      }`}
                    >
                      <div
                        className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                          theme === "dark" ? "translate-x-4" : "translate-x-0"
                        }`}
                      />
                    </div>
                  </button>
                )}
                {section.items.map((item, idx) => (
                  <div
                    key={item.label}
                    className={`flex items-center justify-between px-3 py-2.5 text-sm ${
                      idx !== section.items.length - 1 ? "border-b border-recall-border" : ""
                    }`}
                  >
                    <span className="text-recall-text">{item.label}</span>
                    <span className="text-recall-textMuted">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}