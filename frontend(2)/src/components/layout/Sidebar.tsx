import { useState, useEffect } from "react";
import {
  IconHome,
  IconLayoutDashboard,
  IconAffiliate,
  IconFolder,
  IconListCheck,
  IconSettings,
  IconChevronLeft,
  IconChevronRight,
  IconSun,
  IconMoon,
  IconMessage,
  IconX,
} from "@tabler/icons-react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext";
import { useAuth, authFetch } from "../../context/AuthContext";

const BASE_URL = import.meta.env.VITE_API_URL

interface Conversation {
  conversation_id: string
  title: string
  created_at: string
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
  { label: "그래프", icon: IconAffiliate, path: "/graph" },
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

export default function Sidebar({ activeRoomId, onSelectRoom, onNewChat, refreshTrigger }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([])
  // 삭제 중인 대화 ID (중복 클릭 방지 + 로딩 표시용)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // 인증 필요한 API라서 authFetch 사용, 서버가 이미 user_id 기준으로 필터링해서 줌
  const fetchConversations = async () => {
    try {
      const res = await authFetch(`${BASE_URL}/api/conversations`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setConversations(data.conversations ?? [])
    } catch (err) {
      console.error('대화 목록 조회 실패:', err)
    }
  }

  useEffect(() => {
    fetchConversations()
  }, [refreshTrigger])

  // DELETE /api/conversations/{conversation_id} 문서 기준
  const handleDeleteConversation = async (e: React.MouseEvent, conversationId: string) => {
    e.stopPropagation() // 방 열리는 클릭 이벤트로 전파되는 것 방지
    if (!confirm('이 대화를 삭제할까요? 복구할 수 없어요.')) return

    setDeletingId(conversationId)
    try {
      const res = await authFetch(`${BASE_URL}/api/conversations/${conversationId}`, {
        method: 'DELETE',
      })
      const data = await res.json()
      if (!res.ok || data.status === 'error') {
        throw new Error(data.message ?? data.detail ?? '삭제에 실패했어요')
      }
      // 목록에서 제거
      setConversations(prev => prev.filter(c => c.conversation_id !== conversationId))
      // 지금 열려있던 방을 지운 경우 새 채팅 상태로 전환
      if (activeRoomId === conversationId) {
        onNewChat()
      }
    } catch (err) {
      console.error('대화 삭제 실패:', err)
    } finally {
      setDeletingId(null)
    }
  }

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
                <div
                  key={conv.conversation_id}
                  className="group flex items-center justify-between gap-1 px-2 py-1.5 rounded-lg transition-colors"
                  style={{
                    background: activeRoomId === conv.conversation_id ? "var(--bg-elevated)" : "transparent",
                  }}
                >
                  <button
                    onClick={() => { onSelectRoom(conv.conversation_id); navigate("/"); }}
                    className="flex items-center gap-2 min-w-0 flex-1 text-left"
                    style={{
                      color: activeRoomId === conv.conversation_id ? "var(--text-primary)" : "var(--text-secondary)",
                    }}
                  >
                    <IconMessage size={13} stroke={1.5} className="flex-shrink-0" />
                    <span className="text-xs truncate">{conv.title}</span>
                  </button>

                  {/* 삭제 버튼 - 평소엔 숨김, hover 시 노출 */}
                  <button
                    onClick={(e) => handleDeleteConversation(e, conv.conversation_id)}
                    disabled={deletingId === conv.conversation_id}
                    aria-label="대화 삭제"
                    className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 transition disabled:opacity-50"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    <IconX size={13} stroke={1.8} />
                  </button>
                </div>
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