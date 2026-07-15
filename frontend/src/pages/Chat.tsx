//채팅 메인
import { useState, useEffect } from 'react'
import RecentList from '../components/Home/RecentList'
import ChatArea from '../components/Home/ChatArea'

const BASE_URL = import.meta.env.VITE_API_URL

export interface Conversation {
  room_id: string
  title: string
  created_at: string
  updated_at: string
}

export default function Chat() {
  const [conversations, setConversations] = useState<Conversation[]>([]) //전체 대화방 목록 (RecentList 에게)
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null)//현재 열려있는 채팅방 ID

  //백엔드에서 대화방 목록 불러와 저장 // 새 채팅 생성/삭제 후에도 재호출하여 목록 갱신
  const fetchConversations = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/conversations`)
      const data = await res.json()
      setConversations(data.conversations ?? [])
    } catch (err) {
      console.error('목록 조회 실패:', err)
    }
  }
//페이지 첫 로드 시 목록 한 번 불러오기
  useEffect(() => {
    fetchConversations()
  }, []) 

  return (
    <div className="flex gap-4 h-[calc(100vh-80px)]">
      <RecentList
        conversations={conversations}
        activeRoomId={activeRoomId}
        onSelect={(room_id) => setActiveRoomId(room_id)}
        onNewChat={() => setActiveRoomId(null)}
      />
      <ChatArea
        activeRoomId={activeRoomId}
        setActiveRoomId={setActiveRoomId}
        onRoomCreated={fetchConversations}
      />
    </div>
  )
}