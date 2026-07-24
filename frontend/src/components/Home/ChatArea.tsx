import { useState, useEffect, useRef } from 'react'
import { Send, Plus, X, FileText, Mic } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { useToast } from '../../App'

const BASE_URL = import.meta.env.VITE_API_URL

const suggestions = [
  '이 문서 요약해줘',
  '주요 할 일 정리해줘',
  '담당자별 업무 알려줘',
  '중요한 내용 알려줘',
]

interface ChatTask {
  task_id: string
  task: string
  assignee: string | null
  deadline: string | null
  status: string
  priority?: string
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  tasks?: ChatTask[]
}

// 채팅에 연결된 문서/음성 한 건 (입력창 + 버튼으로 선택한 것들)
interface LinkedDoc {
  document_id: string
  filename: string
  type?: string // 'document' | 'voice'
}

interface Props {
  activeRoomId: string | null
  setActiveRoomId: (id: string) => void
  onRoomCreated: () => void
  targetFilename?: string | null
  targetDocumentId?: string | null
  onGoToAnalysis?: (documentId: string | null) => void
}

const TASKS_KEY = 'chatTasks'
const ADDED_KEY = 'addedTaskIds' // 구조: { [roomId]: string[] }

// 그래프/보관함과 동일한 패턴 — 공백·한글 인코딩 차이까지 같은 이름으로 인식해서 중복 제거
const normalizeFilename = (filename: string) => filename.trim().normalize('NFC')

// 새로고침해도 유지되도록 채팅방별 업무 목록을 localStorage에 저장 (task_id 기준 중복 제거)
const saveRoomTasks = (roomId: string, tasks: ChatTask[]) => {
  try {
    const all = JSON.parse(localStorage.getItem(TASKS_KEY) ?? '{}')
    const existing: ChatTask[] = all[roomId] ?? []
    const merged = [...existing]
    tasks.forEach(t => {
      if (!merged.find(e => e.task_id === t.task_id)) merged.push(t)
    })
    all[roomId] = merged
    localStorage.setItem(TASKS_KEY, JSON.stringify(all))
  } catch {}
}

const loadRoomTasks = (roomId: string): ChatTask[] => {
  try {
    const all = JSON.parse(localStorage.getItem(TASKS_KEY) ?? '{}')
    return all[roomId] ?? []
  } catch { return [] }
}

// "추가됨" 상태도 채팅방별로 분리해서 저장 — 다른 방에서 같은 task_id가 또 나와도 서로 안 섞이게
const saveAddedIds = (roomId: string, ids: Set<string>) => {
  try {
    const all = JSON.parse(localStorage.getItem(ADDED_KEY) ?? '{}')
    all[roomId] = [...ids]
    localStorage.setItem(ADDED_KEY, JSON.stringify(all))
  } catch {}
}

const loadAddedIds = (roomId: string | null): Set<string> => {
  if (!roomId) return new Set()
  try {
    const all = JSON.parse(localStorage.getItem(ADDED_KEY) ?? '{}')
    return new Set(all[roomId] ?? [])
  } catch { return new Set() }
}

export default function ChatArea({ activeRoomId, setActiveRoomId, onRoomCreated, targetFilename, targetDocumentId, onGoToAnalysis }: Props) {
  const { showToast } = useToast()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [addedTaskIds, setAddedTaskIds] = useState<Set<string>>(new Set())
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  // loading state는 비동기라 useEffect 안에서 즉시 참조가 안 되므로 ref로 동기 추적
  const loadingRef = useRef(false)
  // room을 막 생성한 직후엔, 문서 연결(linkDocumentToRoom)들이 다 끝나기 전에
  // activeRoomId 변경으로 트리거된 useEffect가 서버 재조회를 해서 칩이 줄어드는 걸 방지하는 플래그
  const justCreatedRoomRef = useRef(false)

  // 이 채팅방에 연결된 문서/음성 목록 (+ 버튼으로 선택한 것들) — 서버 기준
  const [linkedDocs, setLinkedDocs] = useState<LinkedDoc[]>([])
  const [showPicker, setShowPicker] = useState(false)
  const [allDocs, setAllDocs] = useState<LinkedDoc[]>([])
  const [pickerLoading, setPickerLoading] = useState(false)
  const [pendingSelected, setPendingSelected] = useState<Set<string>>(new Set())

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 채팅방이 바뀔 때마다 그 방의 "추가됨" 상태를 새로 불러옴 (다른 방 상태가 섞여 보이지 않도록)
  useEffect(() => {
    setAddedTaskIds(loadAddedIds(activeRoomId))
  }, [activeRoomId])

  // 서버에서 이 채팅방에 연결된 문서 목록을 가져옴
  const fetchRoomDocuments = async (roomId: string): Promise<LinkedDoc[]> => {
    try {
      const res = await fetch(`${BASE_URL}/api/rooms/${roomId}/documents`)
      const data = await res.json()
      if (data.status === 'success') {
        return (data.documents ?? []).map((d: any) => ({
          document_id: d.document_id,
          filename: d.title,
          type: d.type,
        }))
      }
      return []
    } catch (err) {
      console.error('연결된 문서 목록 조회 실패:', err)
      return []
    }
  }

  // 문서를 채팅방에 연결 (서버 반영)
  const linkDocumentToRoom = async (roomId: string, documentId: string) => {
    try {
      const res = await fetch(`${BASE_URL}/api/rooms/${roomId}/documents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_id: documentId }),
      })
      const data = await res.json()
      if (data.status !== 'success') {
        console.error('문서 연결 실패:', data.error ?? data.message)
        showToast('문서 연결에 실패했어요', 'error')
      }
    } catch (err) {
      console.error('문서 연결 요청 실패:', err)
      showToast('문서 연결에 실패했어요', 'error')
    }
  }

  // 문서를 채팅방에서 연결 해제 (서버 반영, 문서 자체는 삭제 안 됨)
  const unlinkDocumentFromRoom = async (roomId: string, documentId: string) => {
    try {
      const res = await fetch(`${BASE_URL}/api/rooms/${roomId}/documents/${documentId}`, {
        method: 'DELETE',
      })
      const data = await res.json()
      if (data.status !== 'success') {
        console.error('문서 연결 해제 실패:', data.error ?? data.message)
        showToast('문서 연결 해제에 실패했어요', 'error')
      }
    } catch (err) {
      console.error('문서 연결 해제 요청 실패:', err)
      showToast('문서 연결 해제에 실패했어요', 'error')
    }
  }

  // 채팅방이 바뀔 때마다 연결된 문서 목록을 서버에서 새로 불러옴.
  // 아직 채팅방이 없는 새 채팅인데 업로드 직후 받은 targetFilename/targetDocumentId가 있으면
  // (Pipeline에서 막 업로드해서 들어온 경우) 그 문서 1개를 미리 칩으로 보여줌
  useEffect(() => {
    if (!activeRoomId) {
      if (targetDocumentId && targetFilename) {
        setLinkedDocs([{ document_id: targetDocumentId, filename: targetFilename, type: 'document' }])
      } else {
        setLinkedDocs([])
      }
      return
    }

    // handleSend에서 막 room을 생성하고 문서들을 연결하는 중이면,
    // 그 연결이 다 끝나기 전에 서버 조회가 끼어들어 칩 개수가 줄어드는 걸 방지
    if (justCreatedRoomRef.current) {
      justCreatedRoomRef.current = false
      return
    }

    fetchRoomDocuments(activeRoomId).then(async (docs) => {
      // 업로드 직후 처음 들어온 방인데, 서버엔 아직 연결이 안 돼있으면 지금 연결해줌
      if (docs.length === 0 && targetDocumentId && targetFilename) {
        await linkDocumentToRoom(activeRoomId, targetDocumentId)
        setLinkedDocs([{ document_id: targetDocumentId, filename: targetFilename, type: 'document' }])
      } else {
        setLinkedDocs(docs)
      }
    })
  }, [activeRoomId, targetDocumentId, targetFilename])

  useEffect(() => {
    if (!activeRoomId) {
      setMessages([])
      return
    }
    // 전송 처리 중에는 handleSend에서 setActiveRoomId가 호출되면서 이 effect도 같이 실행됨
    // → 이때 메시지를 덮어쓰면 방금 보낸 메시지가 사라지므로 가드
    if (loadingRef.current) return

    fetch(`${BASE_URL}/api/conversations/${activeRoomId}/messages`)
      .then(r => r.json())
      .then(data => {
        const msgs: Message[] = (data.messages ?? []).map((m: any) => ({
          id: m.message_id,
          role: m.role as 'user' | 'assistant',
          text: m.content,
        }))
        // 업무 목록은 백엔드 메시지 응답에 포함되지 않아 localStorage에서 복원,
        // 가장 최근 assistant 메시지에 다시 매칭
        const roomTasks = loadRoomTasks(activeRoomId)
        if (roomTasks.length > 0) {
          const lastAssistantIdx = [...msgs].reverse().findIndex(m => m.role === 'assistant')
          if (lastAssistantIdx !== -1) {
            const realIdx = msgs.length - 1 - lastAssistantIdx
            msgs[realIdx].tasks = roomTasks
          }
        }
        setMessages(msgs)
      })
      .catch(err => console.error('기록 불러오기 실패:', err))
  }, [activeRoomId])

  const createRoom = async (title: string): Promise<string> => {
    const res = await fetch(`${BASE_URL}/api/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
    if (!res.ok) throw new Error('채팅방 생성 실패')
    const data = await res.json()
    return data.room_id
  }

  const handleAddTask = async (task: ChatTask) => {
    try {
      const res = await fetch(`${BASE_URL}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: task.task,
          assignee: task.assignee ?? null,
          deadline: task.deadline ?? null,
          status: 'todo',
          priority: task.priority ?? 'medium',
          room_id: activeRoomId,
          document_id: null, // 채팅 기반 업무는 특정 문서와 연결하지 않음
        }),
      })
      if (!res.ok) throw new Error()
      const data = await res.json()
      if (!data.error) {
        setAddedTaskIds(prev => {
          const next = new Set(prev).add(task.task_id)
          if (activeRoomId) saveAddedIds(activeRoomId, next)
          return next
        })
      }
    } catch {}
  }

  // + 버튼 클릭 — 보관함 문서/음성 목록을 불러와서 선택 팝오버를 염
const openPicker = () => {
  setPendingSelected(new Set(linkedDocs.map(d => d.document_id)))
  setShowPicker(true)
  if (allDocs.length === 0) {
    setPickerLoading(true)
    fetch(`${BASE_URL}/api/documents`)
      .then(r => r.json())
      .catch(() => ({ documents: [] }))
      .then((docRes: any) => {
        const docs: LinkedDoc[] = (docRes.documents ?? [])
          .filter((d: any) => d.type !== 'voice')
          .map((d: any) => ({ document_id: d.document_id, filename: d.filename, type: 'document' }))
        // 같은 이름(공백/인코딩 차이 포함) 문서는 첫 번째 것만 남김
        const unique = docs.filter((d, i, self) =>
          i === self.findIndex(x => normalizeFilename(x.filename) === normalizeFilename(d.filename))
        )
        setAllDocs(unique)
      })
      .catch(err => console.error('문서 목록 불러오기 실패:', err))
      .finally(() => setPickerLoading(false))
  }
}

  const togglePending = (id: string) => {
    setPendingSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // 선택 완료 — 이전 선택과 비교해서 새로 추가된 건 연결 API, 빠진 건 해제 API 호출
  const confirmSelection = async () => {
    const selected = allDocs.filter(d => pendingSelected.has(d.document_id))
    const prevIds = new Set(linkedDocs.map(d => d.document_id))
    const newIds = new Set(selected.map(d => d.document_id))

    const added = selected.filter(d => !prevIds.has(d.document_id))
    const removed = linkedDocs.filter(d => !newIds.has(d.document_id))

    setLinkedDocs(selected)
    if (activeRoomId) {
      // 채팅방이 이미 있으면 즉시 서버에 반영
      await Promise.all([
        ...added.map(d => linkDocumentToRoom(activeRoomId, d.document_id)),
        ...removed.map(d => unlinkDocumentFromRoom(activeRoomId, d.document_id)),
      ])
    }
    // 채팅방이 아직 없는 새 채팅이면, room이 생성되는 시점(handleSend)에 한꺼번에 연결됨
    setShowPicker(false)
  }

  // 칩의 x 버튼 — 연결 해제
  const removeLinkedDoc = async (documentId: string) => {
    const next = linkedDocs.filter(d => d.document_id !== documentId)
    setLinkedDocs(next)
    if (activeRoomId) {
      await unlinkDocumentFromRoom(activeRoomId, documentId)
    }
  }

  const handleSend = async (overrideText?: string) => {
    const userText = (overrideText ?? input).trim()
    if (!userText || loading) return

    setInput('')
    setLoading(true)
    loadingRef.current = true

    let roomId = activeRoomId
    if (!roomId) {
      try {
        justCreatedRoomRef.current = true // setActiveRoomId가 useEffect를 트리거하기 전에 미리 표시
        roomId = await createRoom(userText)
        setActiveRoomId(roomId)
        onRoomCreated()
        // 방 생성 전에 + 버튼으로 미리 골라둔 문서가 있으면, 새로 생긴 room에 정식으로 연결
        if (linkedDocs.length > 0) {
          await Promise.all(linkedDocs.map(d => linkDocumentToRoom(roomId!, d.document_id)))
        }
      } catch {
        justCreatedRoomRef.current = false
        setLoading(false)
        loadingRef.current = false
        return
      }
    }

    const loadingMsgId = `loading_${Date.now()}`
    setMessages(prev => [
      ...prev,
      { id: `user_${Date.now()}`, role: 'user', text: userText },
      { id: loadingMsgId, role: 'assistant', text: '...' },
    ])

    try {
      abortControllerRef.current = new AbortController()

      const res = await fetch(`${BASE_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: roomId,
          content: userText,
          source: linkedDocs.length > 0 ? 'pdf' : 'text',
          target_document_ids: linkedDocs.map(d => d.document_id),
        }),
        signal: abortControllerRef.current.signal,
      })

      if (!res.ok) throw new Error(`HTTP error: ${res.status}`)
      const data = await res.json()
      const answerText = data.answer ?? data.error ?? '응답을 받지 못했어요.'
      const tasks = Array.isArray(data.tasks) && data.tasks.length > 0 ? data.tasks : undefined

      if (tasks && roomId) saveRoomTasks(roomId, tasks)

      setMessages(prev =>
        prev.map(m =>
          m.id === loadingMsgId ? { ...m, text: answerText, tasks } : m
        )
      )
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // 사용자가 직접 중지한 경우는 에러로 취급하지 않고 로딩 메시지만 제거
        setMessages(prev => prev.filter(m => m.id !== loadingMsgId))
      } else {
        setMessages(prev =>
          prev.map(m =>
            m.id === loadingMsgId
              ? { ...m, text: '오류가 발생했어요. 백엔드 연결을 확인해주세요.' }
              : m
          )
        )
      }
    } finally {
      setLoading(false)
      loadingRef.current = false
      onRoomCreated()
    }
  }

  const started = messages.length > 0

  return (
    <div className="flex-1 flex flex-col">

      {/* 연결된 문서/음성 칩 — 선택된 게 있을 때만 보임 */}
      {linkedDocs.length > 0 && (
        <div className="mb-3 flex items-center gap-2 flex-wrap">
          {linkedDocs.map((doc) => (
            <div
              key={doc.document_id}
              className="group flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/30 pl-2.5 pr-1.5 py-1.5 rounded-full"
            >
              {doc.type === 'voice' ? <Mic size={12} /> : <FileText size={12} />}
              <button
                onClick={() => doc.type !== 'voice' && onGoToAnalysis?.(doc.document_id)}
                className={`truncate max-w-[160px] ${doc.type !== 'voice' ? 'hover:underline' : ''}`}
                title={doc.filename}
              >
                {doc.filename}
              </button>
              <button
                onClick={() => removeLinkedDoc(doc.document_id)}
                className="opacity-0 group-hover:opacity-100 transition flex-shrink-0 text-blue-400 hover:text-red-400"
                aria-label="연결 해제"
              >
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      {!started && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white mb-2">
              무엇을 도와드릴까요?
            </h2>
            <p className="text-sm text-gray-400">
              회의록 분석, 업무 정리, 일정 관리 등 무엇이든 물어보세요
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => handleSend(s)}
                className="text-left p-3 bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-xl text-xs text-gray-600 dark:text-gray-300 hover:border-blue-300 dark:hover:border-blue-700 hover:text-blue-500 transition"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {started && (
        <div className="flex-1 overflow-y-auto flex flex-col gap-4 mb-4 pr-1">
          {messages.map((msg) => (
            <div key={msg.id} className={`group flex gap-3 items-start ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>

              <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${
                msg.role === 'assistant' ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-600'
              }`}>
                <span className={`text-xs font-medium ${
                  msg.role === 'assistant' ? 'text-white' : 'text-gray-600 dark:text-gray-200'
                }`}>
                  {msg.role === 'assistant' ? 'AI' : '나'}
                </span>
              </div>

              <div className="flex flex-col gap-2 max-w-lg">
                <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'assistant'
                    ? 'bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 text-gray-700 dark:text-gray-200'
                    : 'bg-blue-600 text-white'
                }`}>
                  {msg.text === '...' && loading
                    ? <span className="animate-pulse text-gray-400">응답 생성 중...</span>
                    : msg.role === 'user'
                      ? msg.text
                      : (
                        <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-0.5 prose-li:my-0 prose-ul:my-1 prose-ol:my-1 [&_*]:text-gray-700 dark:[&_*]:text-gray-200">
                          <ReactMarkdown>{msg.text}</ReactMarkdown>
                        </div>
                      )
                  }
                </div>

                {msg.role === 'assistant' && msg.tasks && msg.tasks.length > 0 && (
                  <div className="bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-2xl p-3 flex flex-col gap-2">
                    <p className="text-[10px] text-gray-400 dark:text-gray-500 font-medium">업무에 추가할 항목을 선택하세요</p>
                    {msg.tasks.map((task) => {
                      const isAdded = addedTaskIds.has(task.task_id)
                      return (
                        <div key={task.task_id} className="flex items-center justify-between gap-2 py-1.5 border-b border-gray-50 dark:border-gray-700 last:border-0">
                          <div className="flex flex-col gap-0.5">
                            <span className="text-xs text-gray-700 dark:text-gray-200">{task.task}</span>
                            <span className="text-[10px] text-gray-400">
                              {task.assignee && `${task.assignee}`}
                              {task.assignee && task.deadline && ' · '}
                              {task.deadline && `${task.deadline}`}
                            </span>
                          </div>
                          <button
                            onClick={() => handleAddTask(task)}
                            disabled={isAdded}
                            className={`flex-shrink-0 text-[10px] px-3 py-1 rounded-full border transition ${
                              isAdded
                                ? 'border-green-300 text-green-500 dark:border-green-700 dark:text-green-400'
                                : 'border-blue-300 text-blue-500 hover:bg-blue-50 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-900/20'
                            }`}
                          >
                            {isAdded ? '✓ 추가됨' : '+ 추가'}
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              <button
                onClick={async () => {
                  if (!confirm('이 메시지를 삭제할까요?')) return
                  await fetch(`${BASE_URL}/api/messages/${msg.id}`, { method: 'DELETE' })
                  setMessages(prev => prev.filter(m => m.id !== msg.id))
                }}
                className={`transition self-center flex-shrink-0 text-gray-400 dark:text-gray-500 hover:text-red-400 dark:hover:text-red-400 ${
                  msg.role === 'user' ? 'mr-1' : 'ml-1'
                }`}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6l-1 14H6L5 6"/>
                  <path d="M10 11v6"/>
                  <path d="M14 11v6"/>
                  <path d="M9 6V4h6v2"/>
                </svg>
              </button>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {started && (
        <div className="flex gap-2 mb-3 flex-wrap">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onClick={() => handleSend(s)}
              className="text-xs text-blue-500 border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/30 px-3 py-1.5 rounded-full hover:bg-blue-100 dark:hover:bg-blue-900/50 transition"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-2 items-end bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-2xl p-2 shadow-sm relative">
        <div className="relative flex-shrink-0">
          <button
            onClick={openPicker}
            className="w-8 h-8 rounded-xl flex items-center justify-center bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition"
            aria-label="문서 선택"
          >
            <Plus size={16} className="text-blue-500" />
          </button>

          {showPicker && (
            <>
              {/* 바깥 클릭하면 닫히게 하는 투명 배경 */}
              <div className="fixed inset-0 z-40" onClick={() => setShowPicker(false)} />
              <div
                className="absolute bottom-full left-0 mb-2 w-72 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-50 overflow-hidden"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="px-3.5 py-2.5 border-b border-gray-100 dark:border-gray-700">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-200">문서 선택</span>
                    <button onClick={() => setShowPicker(false)} className="text-gray-400 hover:text-gray-600">
                      <X size={14} />
                    </button>
                  </div>
                  <p className="text-[11px] text-gray-400 leading-tight">선택한 문서 안에서만 답변해요.</p>
                </div>

                <div className="p-1.5 flex flex-col max-h-64 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 dark:[&::-webkit-scrollbar-thumb]:bg-gray-600 [&::-webkit-scrollbar-track]:bg-transparent">
                  {pickerLoading ? (
                    <p className="text-xs text-gray-400 text-center py-4">불러오는 중...</p>
                  ) : allDocs.length === 0 ? (
                    <p className="text-xs text-gray-400 text-center py-4">업로드된 문서가 없어요</p>
                  ) : (
                    allDocs.map((doc) => {
                      const checked = pendingSelected.has(doc.document_id)
                      return (
                        <label
                          key={doc.document_id}
                          className={`flex items-center gap-2.5 px-2 py-2 rounded-lg cursor-pointer transition flex-shrink-0 ${
                            checked ? 'bg-blue-50 dark:bg-blue-900/30' : 'hover:bg-gray-50 dark:hover:bg-gray-700'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => togglePending(doc.document_id)}
                            className="flex-shrink-0"
                          />
                          {doc.type === 'voice' ? (
                            <Mic size={15} className="text-blue-400 flex-shrink-0" />
                          ) : (
                            <FileText size={15} className="text-gray-400 flex-shrink-0" />
                          )}
                          <span className="text-xs text-gray-700 dark:text-gray-200 truncate">{doc.filename}</span>
                        </label>
                      )
                    })
                  )}
                </div>

                <div className="px-3.5 py-2.5 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
                  <span className="text-xs text-gray-400">{pendingSelected.size}개 선택됨</span>
                  <button
                    onClick={confirmSelection}
                    className="text-xs text-white bg-blue-600 px-3 py-1.5 rounded-lg hover:bg-blue-700"
                  >
                    선택 완료
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder="메시지를 입력하세요... (Enter로 전송)"
          className="flex-1 text-sm text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 bg-transparent resize-none outline-none px-2 py-1.5 max-h-32"
          rows={1}
        />
        <button
          onClick={loading ? () => abortControllerRef.current?.abort() : () => handleSend()}
          className={`w-8 h-8 rounded-xl flex items-center justify-center transition flex-shrink-0 ${
            loading ? 'bg-red-500 hover:bg-red-600' : input.trim() ? 'bg-blue-600 hover:bg-blue-700' : 'bg-gray-100 dark:bg-gray-700'
          }`}
        >
          {loading ? (
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="white">
              <rect x="6" y="6" width="12" height="12"/>
            </svg>
          ) : (
            <Send size={14} className={input.trim() ? 'text-white' : 'text-gray-300'} />
          )}
        </button>
      </div>
    </div>
  )
}