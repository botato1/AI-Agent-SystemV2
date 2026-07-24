export interface ApiTask {
  task_id: string
  task: string
  assignee: string | null
  deadline: string | null
  status: 'todo' | 'in_progress' | 'done' | 'delayed'
  priority: 'high' | 'medium' | 'low'
  room_id: string | null
  document_id: string | null
  created_at: string
}

export interface NewTaskForm {
  task: string
  assignee: string
  deadline: string
  status: 'todo' | 'in_progress' | 'done' | 'delayed'
  priority: 'high' | 'medium' | 'low'
}

export interface UpdateStatusResponse {
  task: {
    task_id: string
    status: 'todo' | 'in_progress' | 'done' | 'delayed'
  }
  error: string | null
}

export interface UpdatePriorityResponse {
  task: {
    task_id: string
    priority: 'high' | 'medium' | 'low'
  } | null
  error: string | null
}