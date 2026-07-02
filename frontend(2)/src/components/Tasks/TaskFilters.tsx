import type { ApiTask } from './types'

interface Props {
  taskList: ApiTask[]
  activeFilter: string
  onFilterChange: (value: string) => void
}

const filters = [
  { label: '전체',      value: 'all' },
  { label: '해야 할 일', value: 'todo' },
  { label: '진행 중',   value: 'in_progress' },
  { label: '완료',      value: 'done' },
  { label: '지연',      value: 'delayed' },
]

export default function TaskFilters({ taskList, activeFilter, onFilterChange }: Props) {
  return (
    <div className="flex gap-1 mb-5 border-b border-gray-100 dark:border-gray-700">
      {filters.map((f) => (
        <button
          key={f.value}
          onClick={() => onFilterChange(f.value)}
          className={`text-xs px-3 py-2 border-b-2 transition ${
            activeFilter === f.value
              ? 'border-blue-600 text-blue-600 font-medium'
              : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
          }`}
        >
          {f.label}
          <span className="ml-1 text-gray-300">
            {f.value === 'all'
              ? taskList.length
              : taskList.filter(t => t.status === f.value).length}
          </span>
        </button>
      ))}
    </div>
  )
}