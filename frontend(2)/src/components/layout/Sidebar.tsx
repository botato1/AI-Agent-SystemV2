import { useState, useEffect } from "react";
import {
  IconHome,
  IconLayoutDashboard,
  IconGavel,
  IconFolder,
  IconListCheck,
  IconSettings,
  IconChevronLeft,
  IconChevronRight,
  IconSun,
  IconMoon,
  IconMessage,
} from "@tabler/icons-react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext";
import { useAuth } from "../../context/AuthContext";

const BASE_URL = import.meta.env.VITE_API_URL

interface Conversation {
  room_id: string
  title: string
  updated_at: string
}

interface NavItem {
  label: string;
  icon: React.ComponentType<{ size?: number; stroke?: number }>;
  path: string;
}

const primaryNavItems: NavItem[] = [
  { label: "홈", icon: IconHome, path: "/" },
  { label: "대시보드", icon: IconLayoutDashboard, path: "/dashboard" },
  { label: "판례 검색", icon: IconGavel, path: "/graph" },
  { label: "문서 보관함", icon: IconFolder, path: "/documents" },
  { label: "할일", icon: IconListCheck, path: "/tasks" },
];

const secondaryNavItems: NavItem[] = [
  { label: "설정", icon: IconSettings, path: "/settings" },
];

interface SidebarProps {
  activeRoomId: string | null
  onSelectRoom: (id: string) => void
  onNewChat: () => void
  refreshTrigger?: number
}

export default function Sidebar({ activeRoomId, onSelectRoom, refreshTrigger }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([])

  const fetchConversations = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/conversations`)
      const data = await res.json()
      setConversations(data.conversations ?? [])
    } catch (err) {
      console.error('대화 목록 조회 실패:', err)
    }
  }

  useEffect(() => {
    fetchConversations()
  }, [refreshTrigger])

  const isActive = (path: string) => {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  };

  const renderNavItem = (item: NavItem) => {
    const Icon = item.icon;
    const active = isActive(item.path);
    return (
      <button
        key={item.path}
        onClick={() => navigate(item.path)}
        title={collapsed ? item.label : undefined}
        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors w-full text-left ${
          collapsed ? "justify-center" : ""
        }`}
        style={{
          background: active ? "var(--bg-elevated)" : "transparent",
          color: active ? "var(--text-primary)" : "var(--text-secondary)",
          fontWeight: active ? 500 : 400,
        }}
      >
        <Icon size={18} stroke={1.8} />
        {!collapsed && <span>{item.label}</span>}
      </button>
    );
  };

  return (
    <aside
      className={`flex flex-col h-screen transition-all duration-200 flex-shrink-0 ${
        collapsed ? "w-[64px]" : "w-[200px]"
      }`}
      style={{
        background: "var(--bg-primary)",
        borderRight: "1px solid var(--border)",
      }}
    >
      {/* 상단: 로고 + 접기 버튼 */}
      <div className="flex items-center justify-between px-3 py-4">
        {!collapsed && (
          <span className="text-sm font-medium px-1" style={{ color: "var(--text-primary)" }}>
            Agentra
          </span>
        )}
        <button
          onClick={() => setCollapsed((prev) => !prev)}
          className="p-1.5 rounded-md"
          style={{ color: "var(--text-secondary)" }}
        >
          {collapsed ? <IconChevronRight size={16} /> : <IconChevronLeft size={16} />}
        </button>
      </div>

      {/* 핵심 메뉴 */}
      <nav className="flex flex-col gap-1 px-2">
        {primaryNavItems.map(renderNavItem)}
      </nav>

      <div className="my-2 mx-3 h-px" style={{ background: "var(--border)" }} />

      {/* 보조 메뉴 */}
      <nav className="flex flex-col gap-1 px-2">
        {secondaryNavItems.map(renderNavItem)}
      </nav>

      {/* 최근 대화 목록 - 접혔을 땐 숨김 */}
      {!collapsed && (
        <div className="flex flex-col flex-1 min-h-0 mt-2">
          <div className="my-2 mx-3 h-px" style={{ background: "var(--border)" }} />

          <span className="text-xs px-3 mb-1.5" style={{ color: "var(--text-secondary)" }}>
            최근 대화
          </span>

          <div className="flex-1 overflow-y-auto px-2 flex flex-col gap-0.5">
            {conversations.length === 0 ? (
              <p className="text-xs px-2 py-2" style={{ color: "var(--text-secondary)" }}>
                대화 기록이 없어요
              </p>
            ) : (
              conversations.slice(0, 20).map((conv) => (
                <button
                  key={conv.room_id}
                  onClick={() => { onSelectRoom(conv.room_id); navigate("/"); }}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-left w-full transition-colors"
                  style={{
                    background: activeRoomId === conv.room_id ? "var(--bg-elevated)" : "transparent",
                    color: activeRoomId === conv.room_id ? "var(--text-primary)" : "var(--text-secondary)",
                  }}
                >
                  <IconMessage size={13} stroke={1.5} className="flex-shrink-0" />
                  <span className="text-xs truncate">{conv.title}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* 하단: 테마 토글 + 로그아웃 */}
      <div
        className="flex flex-col gap-1 px-2 py-3"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <button
          onClick={toggleTheme}
          className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm w-full text-left ${
            collapsed ? "justify-center" : ""
          }`}
          style={{ color: "var(--text-secondary)" }}
        >
          {theme === "dark" ? <IconSun size={18} stroke={1.8} /> : <IconMoon size={18} stroke={1.8} />}
          {!collapsed && <span>{theme === "dark" ? "라이트 모드" : "다크 모드"}</span>}
        </button>
      </div>
    </aside>
  );
}