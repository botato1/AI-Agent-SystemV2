import { useState, useRef, useEffect } from 'react'
import { Plus, MoreHorizontal } from 'lucide-react'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  useDraggable,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core'
import type { ApiTask, UpdateStatusResponse, UpdatePriorityResponse } from './types'

// ========================
// 타입 정의
// ========================

interface Props {
  taskList: ApiTask[]
  doneIds: Set<string>
  activeFilter: string
  onToggleDone: (taskId: string) => void
  onOpenModal: () => void
  onStatusChange: (taskId: string, newStatus: ApiTask['status']) => void
  onPriorityChange: (taskId: string, newPriority: ApiTask['priority']) => void
  onDelete: (taskId: string) => void
}

interface DropdownProps {
  task: ApiTask
  onStatusChange: (taskId: string, newStatus: ApiTask['status']) => void
  onPriorityChange: (taskId: string, newPriority: ApiTask['priority']) => void
  onDelete: (taskId: string) => void
  onClose: () => void
}

// ========================
// 상수 정의
// ========================

const BASE_URL = import.meta.env.VITE_API_URL

// 우선순위 한글 변환
const priorityLabel: Record<string, string> = {
  high: '높음', medium: '중간', low: '낮음',
}

// 우선순위 색상 (일반 / 완료 상태)
const priorityDot: Record<string, { active: string; done: string }> = {
  high:   { active: 'bg-[#ff8fa3] dark:bg-[#c4607a]', done: 'bg-red-200 dark:bg-[#5a3a3f]' },
  medium: { active: 'bg-[#ffd166] dark:bg-[#b89a40]', done: 'bg-amber-200 dark:bg-[#5a4e2a]' },
  low:    { active: 'bg-[#06d6a0] dark:bg-[#0a9e76]', done: 'bg-green-200 dark:bg-[#1e4a3a]' },
}

// 칸반 컬럼 정의
const columns = [
  { id: 'todo',        title: '해야 할 일', barColor: 'bg-[#555]' },
  { id: 'in_progress', title: '진행 중',    barColor: 'bg-[#ffd166] dark:bg-[#b89a40]' },
  { id: 'done',        title: '완료',       barColor: 'bg-[#06d6a0] dark:bg-[#0a9e76]' },
  { id: 'delayed',     title: '지연',       barColor: 'bg-[#ff8fa3] dark:bg-[#c4607a]' },
]

// 드롭다운 상태 옵션
const statusOptions: { value: ApiTask['status']; label: string }[] = [
  { value: 'todo',        label: '해야 할 일' },
  { value: 'in_progress', label: '진행 중' },
  { value: 'done',        label: '완료' },
  { value: 'delayed',     label: '지연' },
]

// 드롭다운 우선순위 옵션
const priorityOptions: { value: ApiTask['priority']; label: string }[] = [
  { value: 'high',   label: '높음' },
  { value: 'medium', label: '중간' },
  { value: 'low',    label: '낮음' },
]

// ========================
// 유틸리티 함수
// ========================

// 날짜 포맷: "2026-06-12" 또는 "2026년 6월 12일" → "6월 12일"
const formatDeadline = (deadline: string | null | undefined): string => {
  if (!deadline) return '-'

  // "2026년 6월 12일" 형식 처리
  if (deadline.includes('년')) {
    const match = deadline.match(/(\d+)월\s*(\d+)일/)
    if (match) return `${match[1]}월 ${match[2]}일`
  }

  // "2026-06-12" 형식 처리
  const parts = deadline.split('-')
  if (parts.length === 3) {
    const month = parseInt(parts[1], 10)
    const day = parseInt(parts[2], 10)
    if (!isNaN(month) && !isNaN(day)) return `${month}월 ${day}일`
  }

  return '-'
}


type DropdownView = 'main' | 'status' | 'priority' | 'delete'

function TaskDropdown({ task, onStatusChange, onPriorityChange, onDelete, onClose }: DropdownProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [view, setView] = useState<DropdownView>('main') // 현재 보여줄 뷰

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [onClose])

  // 상태 변경 API 호출
  const handleStatusSelect = async (newStatus: ApiTask['status']) => {
    if (newStatus === task.status) { onClose(); return }
    try {
      const res = await fetch(`${BASE_URL}/api/tasks/${task.task_id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      if (!res.ok) throw new Error()
      const data: UpdateStatusResponse = await res.json()
      if (!data.error) onStatusChange(task.task_id, data.task.status)
    } catch {
    } finally { onClose() }
  }

  // 우선순위 변경 API 호출
  const handlePrioritySelect = async (newPriority: ApiTask['priority']) => {
    if (newPriority === task.priority) { onClose(); return }
    try {
      const res = await fetch(`${BASE_URL}/api/tasks/${task.task_id}/priority`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priority: newPriority }),
      })
      if (!res.ok) throw new Error()
      const data: UpdatePriorityResponse = await res.json()
      if (!data.error && data.task) onPriorityChange(task.task_id, data.task.priority)
    } catch {
    } finally { onClose() }
  }

  // 1단계: 상태 / 우선순위 / 삭제 메인 메뉴
  const MainView = () => (
    <>
      <button onClick={() => setView('status')} className="w-full flex items-center justify-between px-3 py-2 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition">
        <div className="flex items-center gap-2">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" strokeDasharray="4 2"/></svg>
          상태
        </div>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
      </button>
      <button onClick={() => setView('priority')} className="w-full flex items-center justify-between px-3 py-2 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition">
        <div className="flex items-center gap-2">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
          우선순위
        </div>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
      </button>
      <div className="my-1 border-t border-gray-100 dark:border-gray-700" />
      <button onClick={() => setView('delete')} className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
        삭제
      </button>
    </>
  )

  // 2단계: 상태 선택 서브메뉴
  const StatusView = () => (
    <>
      <button onClick={() => setView('main')} className="w-full flex items-center gap-1.5 px-3 py-2 text-[10px] text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 border-b border-gray-100 dark:border-gray-700 transition">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6"/></svg>
        상태
      </button>
      {statusOptions.map((opt) => (
        <button key={opt.value} onClick={() => handleStatusSelect(opt.value)}
          className={`w-full flex items-center gap-2 px-3 py-2 text-xs text-left transition ${task.status === opt.value ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'}`}
        >
          {opt.value === 'todo'        && <span className="text-gray-400"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" strokeDasharray="4 2"/></svg></span>}
          {opt.value === 'in_progress' && <span style={{ color: '#b89a40' }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg></span>}
          {opt.value === 'done'        && <span style={{ color: '#0a9e76' }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-5"/></svg></span>}
          {opt.value === 'delayed'     && <span style={{ color: '#c4607a' }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 8v4"/><circle cx="12" cy="16" r="0.5" fill="currentColor"/></svg></span>}
          {opt.label}
          {task.status === opt.value && <span className="ml-auto text-blue-500 text-[10px]">✓</span>}
        </button>
      ))}
    </>
  )

  // 2단계: 우선순위 선택 서브메뉴
  const PriorityView = () => (
    <>
      <button onClick={() => setView('main')} className="w-full flex items-center gap-1.5 px-3 py-2 text-[10px] text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 border-b border-gray-100 dark:border-gray-700 transition">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6"/></svg>
        우선순위
      </button>
      {priorityOptions.map((opt) => (
        <button key={opt.value} onClick={() => handlePrioritySelect(opt.value)}
          className={`w-full flex items-center gap-2 px-3 py-2 text-xs text-left transition ${task.priority === opt.value ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'}`}
        >
          {opt.value === 'high'   && <span style={{ color: '#c4607a' }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 19V5M5 12l7-7 7 7"/></svg></span>}
          {opt.value === 'medium' && <span style={{ color: '#b89a40' }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12h14"/></svg></span>}
          {opt.value === 'low'    && <span style={{ color: '#0a9e76' }}><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12l7 7 7-7"/></svg></span>}
          {opt.label}
          {task.priority === opt.value && <span className="ml-auto text-blue-500 text-[10px]">✓</span>}
        </button>
      ))}
    </>
  )

  // 2단계: 삭제 확인
  const DeleteView = () => (
    <div className="p-3">
      <p className="text-xs text-gray-600 dark:text-gray-300 mb-3 leading-relaxed">이 업무를 삭제할까요?</p>
      <div className="flex gap-2">
        <button onClick={() => setView('main')} className="flex-1 text-xs py-1.5 rounded-lg border border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 transition">취소</button>
        <button onClick={() => { onDelete(task.task_id); onClose() }} className="flex-1 text-xs py-1.5 rounded-lg bg-red-500 text-white hover:bg-red-600 transition">삭제</button>
      </div>
    </div>
  )

  return (
    <div ref={ref} className="absolute right-0 top-6 z-20 w-40 bg-white dark:bg-[#1e1e1e] border border-gray-100 dark:border-gray-700 rounded-xl shadow-lg py-1 overflow-hidden">
      {view === 'main'     && <MainView />}
      {view === 'status'   && <StatusView />}
      {view === 'priority' && <PriorityView />}
      {view === 'delete'   && <DeleteView />}
    </div>
  )
}


function DraggableCard({ task, isDone, onToggleDone, onStatusChange, onPriorityChange, onDelete }: {
  task: ApiTask
  isDone: boolean
  onToggleDone: (task: ApiTask) => void
  onStatusChange: (taskId: string, newStatus: ApiTask['status']) => void
  onPriorityChange: (taskId: string, newPriority: ApiTask['priority']) => void
  onDelete: (taskId: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: task.task_id })
  const [openDropdown, setOpenDropdown] = useState(false)
  const dot = priorityDot[task.priority] ?? priorityDot['medium']

  const style = transform ? {
    transform: `translate(${transform.x}px, ${transform.y}px)`,
    zIndex: 50,
  } : undefined

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className={`rounded-xl border p-3 transition relative cursor-grab active:cursor-grabbing ${
        isDragging
          ? 'opacity-40 shadow-xl'
          : isDone
            ? 'bg-gray-50 border-gray-100 dark:bg-[#181818] dark:border-[#222]'
            : 'bg-white dark:bg-gray-800 border-gray-100 dark:border-gray-700 hover:border-blue-200 dark:hover:border-blue-800 hover:shadow-sm'
      }`}
    >
      {/* 우선순위 도트 + ··· 버튼 */}
      <div className="flex items-start justify-between mb-2">

        {/* 우선순위 도트 — 클릭 시 완료 토글, 드래그 방지 */}
        <div
          className="flex items-center gap-1.5 cursor-pointer"
          onPointerDown={e => e.stopPropagation()}
          onClick={() => onToggleDone(task)}
        >
          <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 transition-all ${isDone ? dot.done : dot.active}`} />
          <span className={`text-xs transition-colors ${isDone ? 'text-gray-300 dark:text-[#333]' : 'text-gray-400 dark:text-gray-500'}`}>
            {priorityLabel[task.priority] ?? task.priority}
          </span>
        </div>

        {/* ··· 버튼 — 드래그 방지 */}
        <div className="relative" onPointerDown={e => e.stopPropagation()}>
          <button
            onClick={() => setOpenDropdown(!openDropdown)}
            className="w-5 h-5 flex items-center justify-center rounded hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <MoreHorizontal size={12} className="text-gray-400 dark:text-gray-500" />
          </button>
          {openDropdown && (
            <TaskDropdown
              task={task}
              onStatusChange={onStatusChange}
              onPriorityChange={onPriorityChange}
              onDelete={onDelete}
              onClose={() => setOpenDropdown(false)}
            />
          )}
        </div>
      </div>

      {/* 업무 제목 — isDone이면 취소선 */}
      <p className={`text-xs font-medium mb-3 leading-relaxed transition-all ${
        isDone ? 'line-through text-gray-300 dark:text-[#444]' : 'text-gray-700 dark:text-gray-200'
      }`}>
        {task.task}
      </p>

      {/* 담당자 + 마감일 */}
      <div className="flex items-center justify-between">
        <span className={`text-xs transition-colors ${isDone ? 'text-gray-300 dark:text-[#333]' : 'text-gray-400'}`}>
          {task.assignee ?? '-'}
        </span>
        <span className={`text-xs transition-colors ${isDone ? 'text-gray-300 dark:text-[#333]' : 'text-gray-400'}`}>
          {formatDeadline(task.deadline)}
        </span>
      </div>
    </div>
  )
}


function DroppableColumn({ col, children }: { col: typeof columns[0]; children: React.ReactNode }) {
  const { isOver, setNodeRef } = useDroppable({ id: col.id })

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col gap-3 min-h-24 rounded-xl transition-colors ${
        isOver ? 'bg-blue-50/50 dark:bg-blue-900/10' : ''
      }`}
    >
      {children}
    </div>
  )
}


export default function TaskBoard({ taskList, doneIds, activeFilter, onToggleDone, onOpenModal, onStatusChange, onPriorityChange, onDelete }: Props) {
  const [activeTask, setActiveTask] = useState<ApiTask | null>(null) // 드래그 중인 카드

  // 8px 이상 움직여야 드래그 시작 (클릭과 구분)
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    })
  )

  // 활성 필터에 맞게 컬럼 필터링
  const filteredColumns = (activeFilter === 'all' ? columns : columns.filter(c => c.id === activeFilter))
    .map(col => ({ ...col, tasks: taskList.filter(t => t.status === col.id) }))

  // 드래그 시작 — 드래그 중인 카드 저장
  const handleDragStart = (event: DragStartEvent) => {
    const task = taskList.find(t => t.task_id === event.active.id)
    if (task) setActiveTask(task)
  }

  // 드래그 종료 — 상태 변경 API 호출 + 실패 시 롤백
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setActiveTask(null)
    if (!over) return

    const taskId = active.id as string
    const newStatus = over.id as ApiTask['status']
    const task = taskList.find(t => t.task_id === taskId)
    if (!task || task.status === newStatus) return

    const validStatuses = ['todo', 'in_progress', 'done', 'delayed']
    if (!validStatuses.includes(newStatus)) return

    // UI 즉시 반영
    onStatusChange(taskId, newStatus)

    // API 호출
    fetch(`${BASE_URL}/api/tasks/${taskId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    }).catch(() => {
      // 실패 시 원래 상태로 롤백
      onStatusChange(taskId, task.status)
    })
  }

  // 동그라미 클릭 — done이면 todo로, 아니면 done으로 실제 상태를 서버에 반영
const handleToggleDone = (task: ApiTask) => {
  const newStatus: ApiTask['status'] = task.status === 'done' ? 'todo' : 'done'

  // UI 즉시 반영
  onStatusChange(task.task_id, newStatus)
  onToggleDone(task.task_id) // 기존 doneIds 로컬 표시도 같이 유지 (있어도 무방)

  fetch(`${BASE_URL}/api/tasks/${task.task_id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: newStatus }),
  }).catch(() => {
    // 실패 시 롤백
    onStatusChange(task.task_id, task.status)
  })
}

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className={`grid gap-4 ${
        filteredColumns.length === 1 ? 'grid-cols-1 max-w-sm' :
        filteredColumns.length === 2 ? 'grid-cols-2' : 'grid-cols-4'
      }`}>
        {filteredColumns.map((col) => (
          <div key={col.id} className="flex flex-col gap-3">

            {/* 컬럼 헤더 */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <div className={`w-[1.5px] h-3.5 rounded-sm ${col.barColor}`} />
                <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">{col.title}</span>
                <span className="text-xs text-gray-400 dark:text-gray-600">{col.tasks.length}</span>
              </div>
              <button onClick={onOpenModal} className="w-5 h-5 flex items-center justify-center rounded hover:bg-gray-100 dark:hover:bg-gray-700">
                <Plus size={12} className="text-gray-400" />
              </button>
            </div>

            {/* 드롭 가능한 컬럼 영역 */}
            <DroppableColumn col={col}>
              {col.tasks.map((task) => (
                <DraggableCard
                  key={task.task_id}
                  task={task}
                  // status가 done이거나 로컬 토글이면 취소선 적용
                  isDone={doneIds.has(task.task_id) || task.status === 'done'}
                  onToggleDone={handleToggleDone}
                  onStatusChange={onStatusChange}
                  onPriorityChange={onPriorityChange}
                  onDelete={onDelete}
                />
              ))}

              {/* 업무 추가 버튼 */}
              <button onClick={onOpenModal} className="w-full py-2 border border-dashed border-gray-200 dark:border-gray-600 rounded-xl text-xs text-gray-300 dark:text-gray-600 hover:border-blue-300 hover:text-blue-400 transition">
                + 업무 추가
              </button>
            </DroppableColumn>
          </div>
        ))}
      </div>

      {/* 드래그 중인 카드 오버레이 — 마우스 커서 위치에 표시 */}
      <DragOverlay>
        {activeTask && (
          <div className="rounded-xl border bg-white dark:bg-gray-800 border-blue-300 dark:border-blue-700 p-3 shadow-xl opacity-95 w-52">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-200">{activeTask.task}</p>
            <div className="flex items-center justify-between mt-2">
              <span className="text-xs text-gray-400">{activeTask.assignee ?? '-'}</span>
              <span className="text-xs text-gray-400">{formatDeadline(activeTask.deadline)}</span>
            </div>
          </div>
        )}
      </DragOverlay>
    </DndContext>
  )
}