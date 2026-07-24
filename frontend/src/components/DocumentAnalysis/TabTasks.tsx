interface Task {
  task_id: string
  task: string
  assignee: string | null
  deadline: string | null
  status: string
  priority: string
}

interface Props {
  analysisData?: any
}

const statusColor: Record<string, string> = {
  '진행중': 'text-blue-500 dark:text-blue-400',
  '완료': 'text-gray-400 dark:text-[#555]',
  '대기': 'text-blue-300 dark:text-[#7aa4c8]',
  'todo': 'text-blue-300 dark:text-[#7aa4c8]', // 백엔드 status 값이 영문일 경우 대비
  'in_progress': 'text-blue-500 dark:text-blue-400',
  'done': 'text-gray-400 dark:text-[#555]',
}

const priorityDot: Record<string, string> = {
  high: 'bg-[#ff8fa3] dark:bg-[#c4607a]',
  mid: 'bg-[#ffd166] dark:bg-[#b89a40]',
  medium: 'bg-[#ffd166] dark:bg-[#b89a40]', // organized.tasks의 priority가 'medium'으로 오는 걸 대비 (medium/mid 둘 다 매핑)
  low: 'bg-[#06d6a0] dark:bg-[#0a9e76]',
}

const priorityLabel: Record<string, string> = {
  high: '높음',
  mid: '보통',
  medium: '보통',
  low: '낮음',
}

const formatDeadline = (deadline: string | null) => {
  if (!deadline) return '기한 없음'
  return new Date(deadline).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })
}

export default function TabTasks({ analysisData }: Props) {
  const tasks: Task[] = analysisData?.organized?.tasks ?? []

  if (tasks.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-12 text-center">
        <p className="text-sm text-gray-400">추출된 Task가 없어요</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      {tasks.map((task) => (
        <div key={task.task_id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4 hover:border-blue-200 dark:hover:border-blue-800 transition">
          <div className="flex items-center justify-between mb-3">
            <span className={`text-xs font-medium ${statusColor[task.status] ?? 'text-gray-400'}`}>{task.status}</span>
            <span className="text-xs text-gray-400">{formatDeadline(task.deadline)}</span>
          </div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">{task.task}</p>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-5 h-5 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center">
                <span className="text-xs text-gray-500 dark:text-gray-400">{task.assignee?.[0] ?? '-'}</span>
              </div>
              <span className="text-xs text-gray-500 dark:text-gray-400">{task.assignee ?? '담당자 없음'}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className={`w-2 h-2 rounded-full ${priorityDot[task.priority] ?? 'bg-gray-300'}`} />
              <span className="text-xs text-gray-400">{priorityLabel[task.priority] ?? task.priority}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}