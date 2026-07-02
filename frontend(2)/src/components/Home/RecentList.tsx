import { FileText, ArrowRight, Plus } from 'lucide-react'

interface Conversation {
  room_id: string
  title: string
  created_at: string
  updated_at: string
}

interface Props {
  conversations: Conversation[]
  activeRoomId: string | null
  onSelect: (room_id: string) => void
  onNewChat: () => void
}

export default function RecentList({ conversations, activeRoomId, onSelect, onNewChat }: Props) {
  return (
    <div className="w-64 flex flex-col gap-4 flex-shrink-0">
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">최근 대화</h3>
          <button className="text-xs text-blue-500 flex items-center gap-1 hover:underline">
            전체 보기 <ArrowRight size={10} />
          </button>
        </div>
        {/*대화 목록 영역*/}
        <div className="flex flex-col gap-2">
          {(conversations ?? []).length === 0 && (
            <p className="text-xs text-gray-400 text-center py-4">대화 기록이 없어요</p>
          )}
          {/*대화 목록 하나씩 카드로 렌더링*/}
          {(conversations ?? []).map((item) => (
            <div
              key={item.room_id}  //React가 리스트 항목을 구분하는 고유Key (room_id사용)
              onClick={() => onSelect(item.room_id)}
              className={`bg-white dark:bg-gray-800 rounded-xl p-3 border transition cursor-pointer ${
                activeRoomId === item.room_id
                  ? 'border-blue-400 dark:border-blue-500'
                  : 'border-gray-100 dark:border-gray-700 hover:border-blue-200'
              }`}
            >
              <div className="flex items-start gap-2">
                {/*왼쪽 아이콘 박스*/}
                <div className="w-7 h-7 bg-blue-50 dark:bg-blue-900/30 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5">
                  <FileText size={12} className="text-blue-400" />
                </div>
                {/*오른쪽 텍스트 영역*/}
                <div className="flex-1 min-w-0">
                  {/* min-w-0: flex 안에서 텍스트가 공간보다 길면 잘라서 ...으로 보이는 truncate가 정상 작동하게 함 */} 
                  <p className="text-xs font-medium text-gray-700 dark:text-gray-200 truncate">{item.title}</p>
                  <p className="text-xs text-gray-400">
                    {/* updated_at(ISO 문자열) → Date 객체로 변환 → 한국 날짜 형식으로 표시 */}
                    {new Date(item.updated_at).toLocaleDateString('ko-KR')}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={onNewChat}
        className="w-full flex items-center justify-center gap-2 py-2.5 border border-dashed border-gray-200 dark:border-gray-600 rounded-xl text-xs text-gray-400 hover:border-blue-300 hover:text-blue-400 transition"
      >
        <Plus size={13} /> 새 채팅 시작
      </button>
    </div>
  )
}