// 대시보드 페이지 - 현재는 더미 데이터, 추후 API 연동 예정

const statCards = [
  { label: '진행 중인 사건', value: '12', sub: '이번 달 3건 신규', icon: '📁' },
  { label: '검토 대기 문서', value: '5', sub: '오늘 2건 업로드됨', icon: '📄' },
  { label: '이번 주 할일', value: '8', sub: '3건 완료', icon: '✅' },
  { label: 'AI 대화', value: '24', sub: '이번 달 누적', icon: '💬' },
]

const recentDocs = [
  { name: '강남 오피스텔 임대차계약서.pdf', time: '2시간 전', status: '분석 완료', statusType: 'done' },
  { name: '매매계약서_수정본.docx', time: '어제', status: '분석 중', statusType: 'ing' },
  { name: '전세계약 분쟁 판례.pdf', time: '3일 전', status: '분석 완료', statusType: 'done' },
]

const recentTasks = [
  { name: '계약서 위험조항 검토', status: '대기 중', statusType: 'wait' },
  { name: '판례 검색 보고서 작성', status: '진행 중', statusType: 'ing' },
  { name: '의뢰인 상담 준비', status: '완료', statusType: 'done' },
]

const recentChats = [
  { title: '강남 오피스텔 임대차 계약 검토', time: '2시간 전', count: 8 },
  { title: '매매계약 분쟁 판례 검색', time: '어제', count: 15 },
  { title: '전세보증금 반환 소송 준비', time: '3일 전', count: 6 },
]

// 상태별 색상
const badgeStyle: Record<string, React.CSSProperties> = {
  done: { background: 'rgba(76,175,130,0.15)', color: '#4caf82' },
  ing: { background: 'rgba(59,130,246,0.15)', color: '#60a5fa' },
  wait: { background: 'rgba(234,179,8,0.15)', color: '#ca8a04' },
}

export default function Dashboard() {
  return (
    <div className="p-6 flex flex-col gap-4 overflow-y-auto" style={{ height: '100vh' }}>
      {/* 헤더 */}
      <div>
        <h1 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          대시보드
        </h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          전체 현황을 한눈에 확인하세요
        </p>
      </div>

      {/* 현황 카드 4개 */}
      <div className="grid grid-cols-4 gap-3">
        {statCards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl p-4"
            style={{
              background: 'var(--bg-primary)',
              border: '0.5px solid var(--border)',
            }}
          >
            <p className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>
              {card.icon} {card.label}
            </p>
            <p className="text-2xl font-medium" style={{ color: 'var(--text-primary)' }}>
              {card.value}
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
              {card.sub}
            </p>
          </div>
        ))}
      </div>

      {/* 최근 문서 + 할일 */}
      <div className="grid grid-cols-2 gap-3">
        {/* 최근 분석 문서 */}
        <div
          className="rounded-xl p-4"
          style={{ background: 'var(--bg-primary)', border: '0.5px solid var(--border)' }}
        >
          <p className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            최근 분석 문서
          </p>
          <div className="flex flex-col">
            {recentDocs.map((doc, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-2"
                style={{
                  borderBottom: i < recentDocs.length - 1 ? '0.5px solid var(--border)' : 'none',
                }}
              >
                <div>
                  <p className="text-xs font-medium truncate max-w-[180px]" style={{ color: 'var(--text-primary)' }}>
                    {doc.name}
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                    {doc.time}
                  </p>
                </div>
                <span
                  className="text-xs px-2 py-0.5 rounded-md flex-shrink-0"
                  style={badgeStyle[doc.statusType]}
                >
                  {doc.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 할일 현황 */}
        <div
          className="rounded-xl p-4"
          style={{ background: 'var(--bg-primary)', border: '0.5px solid var(--border)' }}
        >
          <p className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            할일 현황
          </p>
          <div className="flex flex-col">
            {recentTasks.map((task, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-2"
                style={{
                  borderBottom: i < recentTasks.length - 1 ? '0.5px solid var(--border)' : 'none',
                }}
              >
                <p className="text-xs" style={{ color: 'var(--text-primary)' }}>
                  {task.name}
                </p>
                <span
                  className="text-xs px-2 py-0.5 rounded-md flex-shrink-0"
                  style={badgeStyle[task.statusType]}
                >
                  {task.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 최근 AI 대화 */}
      <div
        className="rounded-xl p-4"
        style={{ background: 'var(--bg-primary)', border: '0.5px solid var(--border)' }}
      >
        <p className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
          최근 AI 대화
        </p>
        <div className="flex flex-col">
          {recentChats.map((chat, i) => (
            <div
              key={i}
              className="flex items-center justify-between py-2 cursor-pointer hover:opacity-80 transition"
              style={{
                borderBottom: i < recentChats.length - 1 ? '0.5px solid var(--border)' : 'none',
              }}
            >
              <div>
                <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                  {chat.title}
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                  {chat.time} · 메시지 {chat.count}개
                </p>
              </div>
              <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"
                style={{ color: 'var(--text-secondary)', flexShrink: 0 }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}