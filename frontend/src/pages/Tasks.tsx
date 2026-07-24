import { useState, useEffect } from 'react'
import { Plus } from 'lucide-react'
import type { ApiTask } from '../components/Tasks/types'
import TaskFilters from '../components/Tasks/TaskFilters'
import TaskBoard from '../components/Tasks/TaskBoard'
import CreateTaskModal from '../components/Tasks/CreateTaskModal'

const BASE_URL = import.meta.env.VITE_API_URL

export default function Tasks() {
  const [taskList, setTaskList] = useState<ApiTask[]>([])
  const [doneIds, setDoneIds] = useState<Set<string>>(new Set())
  const [activeFilter, setActiveFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)

  // ── 전체 업무 목록 조회 ──
  useEffect(() => {
    const fetchTasks = async () => {
      try {
        setLoading(true)
        setError(null)

        const res = await fetch(`${BASE_URL}/api/tasks`)
        if (!res.ok) throw new Error(`서버 오류 (${res.status})`)

        const data = await res.json()
        if (data.error) {
          setError(data.error)
          setTaskList([])
        } else {
          setTaskList(data.tasks)
          setDoneIds(new Set(data.tasks.filter((t: ApiTask) => t.status === 'done').map((t: ApiTask) => t.task_id)))
        }
      } catch {
        setError('업무 목록을 불러오지 못했습니다.')
        setTaskList([])
      } finally {
        setLoading(false)
      }
    }

    fetchTasks()
  }, [])

  const handleTaskCreated = (newTask: ApiTask) => {
    setTaskList(prev => [newTask, ...prev])
    if (newTask.status === 'done') {
      setDoneIds(prev => new Set(prev).add(newTask.task_id))
    }
  }

  const toggleDone = (taskId: string) => {
    setDoneIds(prev => {
      const next = new Set(prev)
      next.has(taskId) ? next.delete(taskId) : next.add(taskId)
      return next
    })
  }

  const handleStatusChange = (taskId: string, newStatus: ApiTask['status']) => {
  setTaskList(prev =>
    prev.map(t => t.task_id === taskId ? { ...t, status: newStatus } : t)
  )
}

const handlePriorityChange = (taskId: string, newPriority: ApiTask['priority']) => {
  setTaskList(prev =>
    prev.map(t => t.task_id === taskId ? { ...t, priority: newPriority } : t)
  )
}

const handleTaskDelete = async (taskId: string) => {
  try {
    const res = await fetch(`${BASE_URL}/api/tasks/${taskId}`, { method: 'DELETE' })
    if (!res.ok) throw new Error()
    const data = await res.json()
    if (!data.error && data.task?.deleted) {
      setTaskList(prev => prev.filter(t => t.task_id !== taskId))
    }
  } catch {
    // 추후 toast 연결
  }
}


  return (
    <div>
      {showModal && (
        <CreateTaskModal
          onClose={() => setShowModal(false)}
          onCreated={handleTaskCreated}
        />
      )}

      {/* 헤더 */}
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-bold text-gray-800 dark:text-white">업무 (Task)</h1>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1.5 text-xs text-white bg-blue-600 px-3 py-2 rounded-lg hover:bg-blue-700"
        >
          <Plus size={13} /> 새 업무
        </button>
      </div>

      {/* 필터 탭 */}
      <TaskFilters
        taskList={taskList}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
      />

      {/* 로딩 */}
      {loading && (
        <div className="flex items-center justify-center py-20 text-sm text-gray-400">
          업무 목록을 불러오는 중...
        </div>
      )}

      {/* 에러 */}
      {!loading && error && (
        <div className="flex items-center justify-center py-20 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* 빈 목록 */}
      {!loading && !error && taskList.length === 0 && (
        <div className="flex items-center justify-center py-20 text-sm text-gray-400">
          등록된 업무가 없습니다.
        </div>
      )}

      {/* 칸반 보드 */}
      {!loading && !error && taskList.length > 0 && (
        <TaskBoard
  taskList={taskList}
  doneIds={doneIds}
  activeFilter={activeFilter}
  onToggleDone={toggleDone}
  onOpenModal={() => setShowModal(true)}
  onStatusChange={handleStatusChange}
  onPriorityChange={handlePriorityChange}
  onDelete={handleTaskDelete}
/>
      )}
    </div>
  )
}