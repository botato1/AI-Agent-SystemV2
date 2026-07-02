import { useState } from 'react'
import { useToast } from '../App'
import { useAuth } from '../context/AuthContext'

const BASE_URL = import.meta.env.VITE_API_URL

// 함수 밖에 정의 - 리렌더링 시 재생성 방지 (input 포커스 유지)
const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div
    className="rounded-xl p-5"
    style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}
  >
    <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--text-secondary)' }}>
      {title}
    </h2>
    {children}
  </div>
)

const Row = ({ label, desc, children }: { label: string; desc?: string; children: React.ReactNode }) => (
  <div className="flex items-center justify-between py-3 border-b last:border-0" style={{ borderColor: 'var(--border)' }}>
    <div>
      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{label}</p>
      {desc && <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{desc}</p>}
    </div>
    {children}
  </div>
)

const Toggle = ({ value, onChange }: { value: boolean; onChange: () => void }) => (
  <button
    onClick={onChange}
    className="w-10 h-5 rounded-full relative transition-colors flex-shrink-0"
    style={{ background: value ? 'var(--accent)' : 'var(--bg-elevated)' }}
  >
    <div
      className="w-4 h-4 bg-white rounded-full absolute top-0.5 shadow-sm transition-all"
      style={{ left: value ? '22px' : '2px' }}
    />
  </button>
)

export default function Settings() {
  const { showToast } = useToast()
  const { user, logout } = useAuth()

  const [notifications, setNotifications] = useState({
    analysisComplete: true,
    taskDeadline: true,
  })

  const [pwForm, setPwForm] = useState({
    current: '',
    next: '',
    confirm: '',
  })
  const [pwLoading, setPwLoading] = useState(false)

  const toggleNotification = async (key: keyof typeof notifications) => {
    if (!notifications[key] && 'Notification' in window) {
      await Notification.requestPermission()
    }
    setNotifications(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const handleDeleteAllChats = async () => {
    if (!confirm('채팅 기록을 전체 삭제할까요? 복구할 수 없어요.')) return
    try {
      await fetch(`${BASE_URL}/api/conversations`, { method: 'DELETE' })
      showToast('채팅 기록이 삭제되었습니다.', 'success')
    } catch {
      showToast('삭제 중 오류가 발생했어요.', 'error')
    }
  }

  // TODO: 백엔드 비밀번호 변경 엔드포인트 연동 시 여기만 수정
  const handleChangePassword = async () => {
    if (!pwForm.current || !pwForm.next || !pwForm.confirm) {
      showToast('모든 항목을 입력해주세요.', 'error'); return
    }
    if (pwForm.next !== pwForm.confirm) {
      showToast('새 비밀번호가 일치하지 않아요.', 'error'); return
    }
    if (pwForm.next.length < 4) {
      showToast('비밀번호는 4자 이상이어야 해요.', 'error'); return
    }
    setPwLoading(true)
    try {
      // TODO: await fetch(`${BASE_URL}/api/auth/change-password`, { method: 'POST', ... })
      await new Promise(r => setTimeout(r, 500))
      showToast('비밀번호가 변경되었습니다.', 'success')
      setPwForm({ current: '', next: '', confirm: '' })
    } catch {
      showToast('비밀번호 변경에 실패했어요.', 'error')
    } finally {
      setPwLoading(false)
    }
  }

  return (
    <div className="p-6 overflow-y-auto" style={{ height: '100vh' }}>
      <div className="mb-6 max-w-xl">
        <h1 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>설정</h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>앱 설정을 관리하세요</p>
      </div>

      <div className="flex flex-col gap-4 max-w-xl">

        {/* 계정 */}
        <Section title="계정">
          {/* 아이디 표시 */}
          <Row label="아이디" >
            <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
              {user?.userId ?? '-'}
            </span>
          </Row>

          {/* 비밀번호 변경 */}
          <div className="py-3 border-b" style={{ borderColor: 'var(--border)' }}>
            <p className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
              비밀번호 변경
            </p>
            <div className="flex flex-col gap-2">
              <input
                type="password"
                placeholder="현재 비밀번호"
                value={pwForm.current}
                onChange={(e) => setPwForm(prev => ({ ...prev, current: e.target.value }))}
                className="rounded-md px-3 py-2 text-sm outline-none"
                style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              />
              <input
                type="password"
                placeholder="새 비밀번호"
                value={pwForm.next}
                onChange={(e) => setPwForm(prev => ({ ...prev, next: e.target.value }))}
                className="rounded-md px-3 py-2 text-sm outline-none"
                style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              />
              <input
                type="password"
                placeholder="새 비밀번호 확인"
                value={pwForm.confirm}
                onChange={(e) => setPwForm(prev => ({ ...prev, confirm: e.target.value }))}
                className="rounded-md px-3 py-2 text-sm outline-none"
                style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              />
              <button
                onClick={handleChangePassword}
                disabled={pwLoading}
                className="text-sm px-4 py-2 rounded-lg mt-1 transition disabled:opacity-50"
                style={{ background: 'var(--accent)', color: '#fff' }}
              >
                {pwLoading ? '변경 중...' : '비밀번호 변경'}
              </button>
            </div>
          </div>

          {/* 로그아웃 */}
          <Row label="로그아웃" desc="현재 기기에서 로그아웃해요">
            <button
              onClick={logout}
              className="text-xs px-3 py-1.5 rounded-lg transition flex-shrink-0"
              style={{ border: '1px solid var(--danger)', color: 'var(--danger)' }}
            >
              로그아웃
            </button>
          </Row>
        </Section>

        {/* 알림 */}
        <Section title="알림">
          {[
            { key: 'analysisComplete', label: '문서 분석 완료 알림', desc: '분석이 완료되면 알림을 받아요' },
            { key: 'taskDeadline', label: '업무 마감 알림', desc: '업무 마감 1일 전에 알림을 받아요' },
          ].map((item) => (
            <Row key={item.key} label={item.label} desc={item.desc}>
              <Toggle
                value={notifications[item.key as keyof typeof notifications]}
                onChange={() => toggleNotification(item.key as keyof typeof notifications)}
              />
            </Row>
          ))}
        </Section>

        {/* 데이터 */}
        <Section title="데이터">
          <Row label="채팅 기록 전체 삭제" desc="모든 대화 기록을 삭제해요. 복구할 수 없어요.">
            <button
              onClick={handleDeleteAllChats}
              className="text-xs px-3 py-1.5 rounded-lg transition flex-shrink-0"
              style={{ border: '1px solid var(--danger)', color: 'var(--danger)' }}
            >
              삭제하기
            </button>
          </Row>
        </Section>

      </div>
    </div>
  )
}