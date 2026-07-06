import { useState, useEffect, useRef } from 'react'
import { Send, X, FileText, Mic } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { useToast } from '../../App'

const BASE_URL = import.meta.env.VITE_API_URL

const suggestions = [
  '이 계약서의 위험 조항을 찾아줘',
  '유사 판례를 검색해줘',
  '계약서 핵심 내용을 요약해줘',
  '중요한 기일과 조건을 알려줘',
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

interface LinkedDoc {
  document_id: string
  filename: string
  type?: string
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
const ADDED_KEY = 'addedTaskIds'

const normalizeFilename = (filename: string) => filename.trim().normalize('NFC')

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
  const loadingRef = useRef(false)
  const justCreatedRoomRef = useRef(false)
  const docInputRef = useRef<HTMLInputElement>(null)
  const voiceInputRef = useRef<HTMLInputElement>(null)

  const [linkedDocs, setLinkedDocs] = useState<LinkedDoc[]>([])

  // + 버튼 메뉴
  const [showMenu, setShowMenu] = useState(false)
  // 보관함 선택 팝오버
  const [showPicker, setShowPicker] = useState(false)
  const [allDocs, setAllDocs] = useState<LinkedDoc[]>([])
  const [pickerLoading, setPickerLoading] = useState(false)
  const [pendingSelected, setPendingSelected] = useState<Set<string>>(new Set())
  // 업로드 중 상태
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    setAddedTaskIds(loadAddedIds(activeRoomId))
  }, [activeRoomId])

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
    } catch { return [] }
  }

  const linkDocumentToRoom = async (roomId: string, documentId: string) => {
    try {
      await fetch(`${BASE_URL}/api/rooms/${roomId}/documents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_id: documentId }),
      })
    } catch {}
  }

  const unlinkDocumentFromRoom = async (roomId: string, documentId: string) => {
    try {
      await fetch(`${BASE_URL}/api/rooms/${roomId}/documents/${documentId}`, {
        method: 'DELETE',
      })
    } catch {}
  }

  useEffect(() => {
    if (!activeRoomId) {
      if (targetDocumentId && targetFilename) {
        setLinkedDocs([{ document_id: targetDocumentId, filename: targetFilename, type: 'document' }])
      } else {
        setLinkedDocs([])
      }
      return
    }
    if (justCreatedRoomRef.current) {
      justCreatedRoomRef.current = false
      return
    }
    fetchRoomDocuments(activeRoomId).then(async (docs) => {
      if (docs.length === 0 && targetDocumentId && targetFilename) {
        await linkDocumentToRoom(activeRoomId, targetDocumentId)
        setLinkedDocs([{ document_id: targetDocumentId, filename: targetFilename, type: 'document' }])
      } else {
        setLinkedDocs(docs)
      }
    })
  }, [activeRoomId, targetDocumentId, targetFilename])

  useEffect(() => {
    if (!activeRoomId) { setMessages([]); return }
    if (loadingRef.current) return
    fetch(`${BASE_URL}/api/conversations/${activeRoomId}/messages`)
      .then(r => r.json())
      .then(data => {
        const msgs: Message[] = (data.messages ?? []).map((m: any) => ({
          id: m.message_id,
          role: m.role as 'user' | 'assistant',
          text: m.content,
        }))
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

  // ── 문서 업로드 ──────────────────────────────────────────────
  const handleDocUpload = async (file: File) => {
    setUploading(true)
    setShowMenu(false)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('type', 'document')
      formData.append('room_id', '')
      const res = await fetch(`${BASE_URL}/api/documents/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error('업로드 실패')
      const data = await res.json()
      if (data.status === 'error') throw new Error(data.error ?? '처리 실패')

      const newDoc: LinkedDoc = {
        document_id: data.document_id,
        filename: data.filename,
        type: 'document',
      }
      setLinkedDocs(prev => [...prev, newDoc])
      if (activeRoomId) await linkDocumentToRoom(activeRoomId, newDoc.document_id)
      showToast(`${data.filename} 업로드 완료`, 'success')
    } catch (err: any) {
      showToast(err.message ?? '업로드 실패', 'error')
    } finally {
      setUploading(false)
    }
  }

  // ── 음성 업로드 ──────────────────────────────────────────────
  const handleVoiceUpload = async (file: File) => {
    setUploading(true)
    setShowMenu(false)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`${BASE_URL}/api/stt/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error('업로드 실패')
      const data = await res.json()
      if (data.status !== 'success') throw new Error(data.error ?? '업로드 실패')

      const newDoc: LinkedDoc = {
        document_id: data.document_id,
        filename: data.filename,
        type: 'voice',
      }
      setLinkedDocs(prev => [...prev, newDoc])
      if (activeRoomId) await linkDocumentToRoom(activeRoomId, newDoc.document_id)
      showToast(`${data.filename} 업로드 완료`, 'success')
    } catch (err: any) {
      showToast(err.message ?? '업로드 실패', 'error')
    } finally {
      setUploading(false)
    }
  }

  // ── 보관함 선택 ──────────────────────────────────────────────
  const openPicker = () => {
    setPendingSelected(new Set(linkedDocs.map(d => d.document_id)))
    setShowPicker(true)
    setShowMenu(false)
    if (allDocs.length === 0) {
      setPickerLoading(true)
      fetch(`${BASE_URL}/api/documents`)
        .then(r => r.json())
        .catch(() => ({ documents: [] }))
        .then((docRes: any) => {
          const docs: LinkedDoc[] = (docRes.documents ?? [])
            .filter((d: any) => d.type !== 'voice')
            .map((d: any) => ({ document_id: d.document_id, filename: d.filename, type: 'document' }))
          const unique = docs.filter((d, i, self) =>
            i === self.findIndex(x => normalizeFilename(x.filename) === normalizeFilename(d.filename))
          )
          setAllDocs(unique)
        })
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

  const confirmSelection = async () => {
    const selected = allDocs.filter(d => pendingSelected.has(d.document_id))
    const prevIds = new Set(linkedDocs.map(d => d.document_id))
    const newIds = new Set(selected.map(d => d.document_id))
    const added = selected.filter(d => !prevIds.has(d.document_id))
    const removed = linkedDocs.filter(d => !newIds.has(d.document_id))
    setLinkedDocs(selected)
    if (activeRoomId) {
      await Promise.all([
        ...added.map(d => linkDocumentToRoom(activeRoomId, d.document_id)),
        ...removed.map(d => unlinkDocumentFromRoom(activeRoomId, d.document_id)),
      ])
    }
    setShowPicker(false)
  }

  const removeLinkedDoc = async (documentId: string) => {
    setLinkedDocs(prev => prev.filter(d => d.document_id !== documentId))
    if (activeRoomId) await unlinkDocumentFromRoom(activeRoomId, documentId)
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
          document_id: null,
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

  const handleSend = async (overrideText?: string) => {
    const userText = (overrideText ?? input).trim()
    if (!userText || loading) return
    setInput('')
    setLoading(true)
    loadingRef.current = true

    let roomId = activeRoomId
    if (!roomId) {
      try {
        justCreatedRoomRef.current = true
        roomId = await createRoom(userText)
        setActiveRoomId(roomId)
        onRoomCreated()
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
        prev.map(m => m.id === loadingMsgId ? { ...m, text: answerText, tasks } : m)
      )
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setMessages(prev => prev.filter(m => m.id !== loadingMsgId))
      } else {
        setMessages(prev =>
          prev.map(m => m.id === loadingMsgId
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

      {/* 연결된 문서 칩 */}
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
              >
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 시작 전 화면 */}
      {!started && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white mb-2">
              무엇을 도와드릴까요?
            </h2>
            <p className="text-sm text-gray-400">
              계약서 검토, 판례 검색 등 무엇이든 물어보세요
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

      {/* 메시지 목록 */}
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
                                : 'border-blue-300 text-blue-500 hover:bg-blue-50 dark:border-blue-700 dark:text-blue-400'
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
                className={`transition self-center flex-shrink-0 text-gray-400 hover:text-red-400 ${
                  msg.role === 'user' ? 'mr-1' : 'ml-1'
                }`}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6l-1 14H6L5 6"/>
                  <path d="M10 11v6"/><path d="M14 11v6"/>
                  <path d="M9 6V4h6v2"/>
                </svg>
              </button>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {/* 빠른 질문 버튼 */}
      {started && (
        <div className="flex gap-2 mb-3 flex-wrap">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onClick={() => handleSend(s)}
              className="text-xs text-blue-500 border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/30 px-3 py-1.5 rounded-full hover:bg-blue-100 transition"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* 입력창 */}
      <div className="flex gap-2 items-end bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-2xl p-2 shadow-sm relative">

        {/* 숨김 파일 input들 */}
        <input
          ref={docInputRef}
          type="file"
          accept=".pdf,.docx,.txt,.png,.jpg"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleDocUpload(f); e.target.value = '' }}
        />
        <input
          ref={voiceInputRef}
          type="file"
          accept=".mp3,.wav,.m4a,.aac"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleVoiceUpload(f); e.target.value = '' }}
        />

        {/* + 버튼 + 메뉴 */}
        <div className="relative flex-shrink-0">
          <button
            onClick={() => { setShowMenu(prev => !prev); setShowPicker(false) }}
            disabled={uploading}
            className="w-8 h-8 rounded-xl flex items-center justify-center bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition disabled:opacity-50"
            aria-label="파일 추가"
          >
            {uploading
              ? <span className="animate-spin text-blue-500 text-xs">⏳</span>
              : <span className="text-blue-500 text-lg leading-none">+</span>
            }
          </button>

          {/* + 메뉴 팝업 */}
          {showMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowMenu(false)} />
              <div className="absolute bottom-full left-0 mb-2 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-50 overflow-hidden py-1">
                <button
                  onClick={() => { setShowMenu(false); docInputRef.current?.click() }}
                  className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition"
                >
                  <FileText size={15} className="text-gray-400" />
                  문서 업로드
                </button>
                <button
                  onClick={() => { setShowMenu(false); voiceInputRef.current?.click() }}
                  className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition"
                >
                  <Mic size={15} className="text-gray-400" />
                  음성 업로드
                </button>
                <div className="my-1 mx-3 h-px bg-gray-100 dark:bg-gray-700" />
                <button
                  onClick={openPicker}
                  className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition"
                >
                  <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24" className="text-gray-400">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 7h18M3 12h18M3 17h10" />
                  </svg>
                  보관함에서 선택
                </button>
              </div>
            </>
          )}

          {/* 보관함 선택 팝오버 */}
          {showPicker && (
            <>
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
                  <p className="text-[11px] text-gray-400">선택한 문서 안에서만 답변해요.</p>
                </div>
                <div className="p-1.5 flex flex-col max-h-64 overflow-y-auto">
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
                          className={`flex items-center gap-2.5 px-2 py-2 rounded-lg cursor-pointer transition ${
                            checked ? 'bg-blue-50 dark:bg-blue-900/30' : 'hover:bg-gray-50 dark:hover:bg-gray-700'
                          }`}
                        >
                          <input type="checkbox" checked={checked} onChange={() => togglePending(doc.document_id)} className="flex-shrink-0" />
                          <FileText size={15} className="text-gray-400 flex-shrink-0" />
                          <span className="text-xs text-gray-700 dark:text-gray-200 truncate">{doc.filename}</span>
                        </label>
                      )
                    })
                  )}
                </div>
                <div className="px-3.5 py-2.5 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
                  <span className="text-xs text-gray-400">{pendingSelected.size}개 선택됨</span>
                  <button onClick={confirmSelection} className="text-xs text-white bg-blue-600 px-3 py-1.5 rounded-lg hover:bg-blue-700">
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
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
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