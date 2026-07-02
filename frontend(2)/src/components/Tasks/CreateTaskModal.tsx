import { useState } from 'react'
import { X } from 'lucide-react'
import type { ApiTask, NewTaskForm } from './types'

interface Props {
  onClose: () => void
  onCreated: (task: ApiTask) => void
}

const BASE_URL = import.meta.env.VITE_API_URL

const INITIAL_FORM: NewTaskForm = {
  task: '',
  assignee: '',
  deadline: '',
  status: 'todo',
  priority: 'medium',
}

export default function CreateTaskModal({ onClose, onCreated }: Props) {
  const [form, setForm] = useState<NewTaskForm>(INITIAL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const handleChange = (field: keyof NewTaskForm, value: string) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  const handleSubmit = async () => {
    if (!form.task.trim()) {
      setSubmitError('업무 내용을 입력해주세요.')
      return
    }

    try {
      setSubmitting(true)
      setSubmitError(null)

      const res = await fetch(`${BASE_URL}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: form.task.trim(),
          assignee: form.assignee.trim() || null,
          deadline: form.deadline || null,
          status: form.status,
          priority: form.priority,
          room_id: null,
          document_id: null,
        }),
      })

      if (!res.ok) throw new Error(`서버 오류 (${res.status})`)

      const data = await res.json()
      if (data.error) {
        setSubmitError(data.error)
      } else {
        onCreated(data.task)
        onClose()
      }
    } catch {
      setSubmitError('업무 생성 중 오류가 발생했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md bg-white dark:bg-[#1e1e1e] rounded-2xl shadow-xl p-6 mx-4"
        onClick={e => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-semibold text-gray-800 dark:text-white">새 업무 추가</h2>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <X size={14} className="text-gray-400" />
          </button>
        </div>

        <div className="flex flex-col gap-3">

          {/* 업무 내용 */}
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
              업무 내용 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.task}
              onChange={e => handleChange('task', e.target.value)}
              placeholder="업무 내용을 입력하세요"
              className="w-full text-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-[#2a2a2a] text-gray-800 dark:text-white placeholder-gray-300 dark:placeholder-gray-600 focus:outline-none focus:border-blue-400"
            />
          </div>

          {/* 담당자 */}
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">담당자</label>
            <input
              type="text"
              value={form.assignee}
              onChange={e => handleChange('assignee', e.target.value)}
              placeholder="담당자 이름"
              className="w-full text-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-[#2a2a2a] text-gray-800 dark:text-white placeholder-gray-300 dark:placeholder-gray-600 focus:outline-none focus:border-blue-400"
            />
          </div>

          {/* 마감일 */}
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">마감일</label>
            <input
              type="date"
              value={form.deadline}
              onChange={e => handleChange('deadline', e.target.value)}
              className="w-full text-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-[#2a2a2a] text-gray-800 dark:text-white focus:outline-none focus:border-blue-400"
            />
          </div>

          {/* 우선순위 + 상태 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">우선순위</label>
              <select
                value={form.priority}
                onChange={e => handleChange('priority', e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-[#2a2a2a] text-gray-800 dark:text-white focus:outline-none focus:border-blue-400"
              >
                <option value="high">높음</option>
                <option value="medium">중간</option>
                <option value="low">낮음</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">상태</label>
              <select
                value={form.status}
                onChange={e => handleChange('status', e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-[#2a2a2a] text-gray-800 dark:text-white focus:outline-none focus:border-blue-400"
              >
                <option value="todo">해야 할 일</option>
                <option value="in_progress">진행 중</option>
                <option value="done">완료</option>
                <option value="delayed">지연</option>
              </select>
            </div>
          </div>
        </div>

        {submitError && (
          <p className="mt-3 text-xs text-red-400">{submitError}</p>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="text-xs px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 transition"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="text-xs px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition"
          >
            {submitting ? '추가 중...' : '업무 추가'}
          </button>
        </div>
      </div>
    </div>
  )
}