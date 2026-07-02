import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

const BASE_URL = import.meta.env.VITE_API_URL

interface Conversation {
  room_id: string
  title: string
  created_at: string
  updated_at: string
  message_count?: number
  document_count?: number
}

type Status = 'active' | 'done' | 'new'

const STATUS_KEY = 'case-status'

const saveStatus = (roomId: string, status: Status) => {
  try {
    const all = JSON.parse(localStorage.getItem(STATUS_KEY) ?? '{}')
    all[roomId] = status
    localStorage.setItem(STATUS_KEY, JSON.stringify(all))
  } catch {}
}

const loadStatus = (roomId: string, updatedAt: string): Status => {
  try {
    const all = JSON.parse(localStorage.getItem(STATUS_KEY) ?? '{}')
    if (all[roomId]) return all[roomId]
  } catch {}
  // 저장된 상태 없으면 시간 기준 자동 판단
  const diff = Date.now() - new Date(updatedAt).getTime()
  const hours = diff / 1000 / 60 / 60
  if (hours < 1) return 'new'
  return 'active'
}

const STATUS_OPTIONS: { value: Status; label: string; color: string; bg: string }[] = [
  { value: 'active', label: '진행 중', color: '#60a5fa', bg: 'rgba(59,130,246,0.12)' },
  { value: 'done', label: '완료', color: '#4caf82', bg: 'rgba(76,175,130,0.12)' },
  { value: 'new', label: '방금 생성', color: '#ca8a04', bg: 'rgba(234,179,8,0.12)' },
]

const getTimeLabel = (updatedAt: string) => {
  const diff = Date.now() - new Date(updatedAt).getTime()
  const mins = Math.floor(diff / 1000 / 60)
  const hours = Math.floor(mins / 60)
  const days = Math.floor(hours / 24)
  if (mins < 1) return '방금 전'
  if (mins < 60) return `${mins}분 전 업데이트`
  if (hours < 24) return `${hours}시간 전 업데이트`
  if (days < 7) return `${days}일 전 업데이트`
  return new Date(updatedAt).toLocaleDateString('ko-KR')
}

// 상태 배지 + 드롭다운
function StatusBadge({
  roomId, status, onChange
}: {
  roomId: string
  status: Status
  onChange: (s: Status) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const current = STATUS_OPTIONS.find(o => o.value === status)!

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(prev => !prev) }}
        className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md font-medium"
        style={{ background: current.bg, color: current.color, border: 'none', cursor: 'pointer' }}
      >
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: current.color, display: 'inline-block', flexShrink: 0 }} />
        {current.label}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute z-50 rounded-xl py-1.5 flex flex-col"
            style={{
              bottom: '110%',
              right: 0,
              background: 'var(--bg-secondary)',
              border: '0.5px solid var(--border)',
              boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
              minWidth: 120,
            }}
          >
            {STATUS_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={(e) => {
                  e.stopPropagation()
                  onChange(opt.value)
                  saveStatus(roomId, opt.value)
                  setOpen(false)
                }}
                className="flex items-center gap-2 px-3 py-2 text-xs text-left w-full transition-colors"
                style={{
                  color: 'var(--text-primary)',
                  background: status === opt.value ? 'var(--bg-elevated)' : 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: opt.color, display: 'inline-block', flexShrink: 0 }} />
                {opt.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [statuses, setStatuses] = useState<Record<string, Status>>({})

  useEffect(() => {
    const fetch_ = async () => {
      try {
        const res = await fetch(`${BASE_URL}/api/conversations`)
        const data = await res.json()
        const convs: Conversation[] = data.conversations ?? []
        setConversations(convs)
        // 각 대화방 상태 초기화
        const init: Record<string, Status> = {}
        convs.forEach(c => { init[c.room_id] = loadStatus(c.room_id, c.updated_at) })
        setStatuses(init)
      } catch (err) {
        console.error('사건 목록 조회 실패:', err)
      } finally {
        setLoading(false)
      }
    }
    fetch_()
  }, [])

  const handleStatusChange = (roomId: string, status: Status) => {
    setStatuses(prev => ({ ...prev, [roomId]: status }))
  }

  return (
    <div className="p-6 overflow-y-auto" style={{ height: '100vh' }}>
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            사건 목록
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            채팅을 시작하면 사건이 자동으로 생성됩니다
          </p>
        </div>
        <button
          onClick={() => navigate('/')}
          className="text-xs text-white px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 transition"
        >
          + 새 사건
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>불러오는 중...</p>
        </div>
      )}

      {!loading && (
        <div className="grid grid-cols-3 gap-4">
          {conversations.map((conv) => (
            <div
              key={conv.room_id}
              onClick={() => navigate('/', { state: { roomId: conv.room_id } })}
              className="rounded-xl p-4 flex flex-col gap-2 transition-all cursor-pointer"
              style={{
                background: 'var(--bg-primary)',
                border: '0.5px solid var(--border)',
              }}
              onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent-text)'}
              onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
            >
              {/* 제목 */}
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)', lineHeight: 1.4 }}>
                {conv.title}
              </p>

              {/* 시간 */}
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {getTimeLabel(conv.updated_at)}
              </p>

              {/* 메타 */}
              <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ opacity: 0.6 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
                </svg>
                {conv.message_count ?? '-'}
                <span style={{ opacity: 0.4 }}>·</span>
                <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ opacity: 0.6 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                </svg>
                {conv.document_count ?? 0}
              </div>

              {/* 상태 배지 */}
              <div className="flex justify-end mt-1">
                <StatusBadge
                  roomId={conv.room_id}
                  status={statuses[conv.room_id] ?? 'active'}
                  onChange={(s) => handleStatusChange(conv.room_id, s)}
                />
              </div>
            </div>
          ))}

          {/* 새 사건 카드 */}
          <div
            onClick={() => navigate('/')}
            className="rounded-xl flex flex-col items-center justify-center gap-2 cursor-pointer transition-all"
            style={{
              border: '0.5px dashed var(--border)',
              minHeight: 130,
            }}
            onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent-text)'}
            onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
          >
            <span style={{ fontSize: 22, color: 'var(--text-secondary)' }}>+</span>
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>새 채팅 시작하기</span>
          </div>

          {conversations.length === 0 && (
            <div className="col-span-3 flex items-center justify-center py-20 text-center">
              <div>
                <p className="text-sm mb-1" style={{ color: 'var(--text-primary)' }}>아직 사건이 없어요</p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>홈에서 채팅을 시작하면 사건이 자동으로 생성됩니다</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}