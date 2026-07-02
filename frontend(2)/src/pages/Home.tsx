import ChatArea from '../components/Home/ChatArea'

interface Props {
  activeRoomId: string | null
  setActiveRoomId: (id: string | null) => void
  onRoomCreated: () => void
}

export default function Home({ activeRoomId, setActiveRoomId, onRoomCreated }: Props) {
  return (
    <div className="flex flex-col h-screen">
      {/* 상단 헤더 */}
      <div
        className="flex items-center justify-between px-6 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div>
          <h1 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            안녕하세요, 변호사님
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            계약서 검토나 판례 검색을 도와드릴게요
          </p>
        </div>
        <button
          onClick={() => setActiveRoomId(null)}
          className="flex items-center gap-1.5 text-xs text-white px-3 py-2 rounded-lg transition bg-blue-600 hover:bg-blue-700"
        >
          + 새 채팅
        </button>
      </div>

      {/* 채팅 영역 */}
      <div className="flex-1 min-h-0 flex flex-col px-4 pb-4">
        <ChatArea
          activeRoomId={activeRoomId}
          setActiveRoomId={setActiveRoomId}
          onRoomCreated={onRoomCreated}
          targetFilename={null}
          targetDocumentId={null}
          onGoToAnalysis={() => {}}
        />
      </div>
    </div>
  )
}