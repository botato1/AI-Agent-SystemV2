import { useState, useEffect } from 'react'
import { ArrowLeft, CheckCircle, Clock, AlertTriangle } from 'lucide-react'

const BASE_URL = import.meta.env.VITE_API_URL

interface Task {
  task_id: string
  task: string
  assignee: string | null
  priority: string
}

interface DocumentDetail {
  filename: string
  created_at: string
  chroma_status: 'success' | 'pending' | 'failed'
  analysis: {
    summary: string
    keywords: string[]
  }
  organized: {
    tasks: Task[]
    important_points: string[]
    decisions: string[]
  }
}

type Props = {
  documentId: string
  onBack: () => void
}

const priorityColors: Record<string, string> = {
  high: 'bg-red-400',
  medium: 'bg-amber-400',
  low: 'bg-green-400',
}
const priorityLabel: Record<string, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
}

export default function DocumentAnalysis({ documentId, onBack }: Props) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    fetch(`${BASE_URL}/api/documents/${documentId}`)
      .then(r => r.json())
      .then(data => {
        if (data.status === 'success') {
          setDoc(data.document)
        } else {
          setNotFound(true)
        }
      })
      .catch(err => {
        console.error('문서 상세 조회 실패:', err)
        setNotFound(true)
      })
      .finally(() => setLoading(false))
  }, [documentId])

  return (
    <div>
      <div className="flex items-center gap-3 mb-5">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition"
        >
          <ArrowLeft size={16} /> 목록으로
        </button>
        <span className="text-gray-200 dark:text-gray-700">|</span>
        <h1 className="text-sm font-medium text-gray-700 dark:text-gray-200">
          {doc?.filename ?? '불러오는 중...'}
        </h1>
        {doc?.created_at && (
          <span className="text-xs text-gray-400">
            {new Date(doc.created_at).toLocaleDateString('ko-KR')}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {doc?.chroma_status === 'pending' && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-400 flex items-center gap-1">
              <Clock size={11} /> AI 분석 준비 중
            </span>
          )}
          {doc?.chroma_status === 'failed' && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-red-50 dark:bg-red-900/30 text-red-400 flex items-center gap-1">
              <AlertTriangle size={11} /> AI 분석 기능 일시 중단
            </span>
          )}
          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-400 flex items-center gap-1">
            <CheckCircle size={11} /> 분석 완료
          </span>
        </div>
      </div>

      {loading ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-12 text-center">
          <p className="text-gray-400 text-sm">불러오는 중...</p>
        </div>
      ) : notFound || !doc ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-12 text-center">
          <p className="text-gray-400 text-sm">분석 데이터가 없습니다.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-5">
            <p className="text-xs font-medium text-gray-400 mb-2">요약</p>
            <p className="text-sm text-gray-700 dark:text-gray-200 leading-7">
              {doc.analysis?.summary || '요약 내용이 없어요.'}
            </p>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-5">
            <p className="text-xs font-medium text-gray-400 mb-3">키워드</p>
            <div className="flex flex-wrap gap-2">
              {(doc.analysis?.keywords ?? []).length === 0 ? (
                <p className="text-xs text-gray-300">키워드가 없어요.</p>
              ) : (
                doc.analysis.keywords.map((kw) => (
                  <span key={kw} className="text-xs px-3 py-1 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-500 dark:text-blue-400">{kw}</span>
                ))
              )}
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-5">
            <p className="text-xs font-medium text-gray-400 mb-3">추출된 Task</p>
            <div className="flex flex-col gap-2">
              {(doc.organized?.tasks ?? []).length === 0 ? (
                <p className="text-xs text-gray-300">추출된 업무가 없어요.</p>
              ) : (
                doc.organized.tasks.map((task) => (
                  <div key={task.task_id} className="flex items-center gap-3 p-3 rounded-lg border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${priorityColors[task.priority] ?? 'bg-gray-300'}`} />
                    <span className="text-sm text-gray-700 dark:text-gray-200 flex-1">{task.task}</span>
                    {task.assignee && (
                      <span className="text-xs text-gray-400 dark:text-gray-400 bg-white dark:bg-gray-700 px-2 py-0.5 rounded-full border border-gray-100 dark:border-gray-600">{task.assignee}</span>
                    )}
                    <span className="text-xs text-gray-300 dark:text-gray-500">{priorityLabel[task.priority] ?? task.priority}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {doc.organized?.important_points?.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-5">
              <p className="text-xs font-medium text-gray-400 mb-3">주요 내용</p>
              <ul className="flex flex-col gap-1.5 list-disc list-inside">
                {doc.organized.important_points.map((point, i) => (
                  <li key={i} className="text-sm text-gray-700 dark:text-gray-200">{point}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}