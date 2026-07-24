import { useState, useEffect } from 'react'
import { ArrowLeft, FileText, File, Clock, AlertTriangle, Table2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const BASE_URL = import.meta.env.VITE_API_URL

interface TableItem {
  markdown: string
  rows: number
}

interface DocumentDetail {
  filename: string
  created_at: string
  chroma_status: 'success' | 'pending' | 'failed'
  raw: {
    original_text: string
    chunks: any[]
    tables: TableItem[]
    charts: any[]  // 아직 데이터 없어서 형식 미확정, 들어오면 추가 연동
  }
}

type Props = {
  documentId: string
  onBack: () => void
}

const formatDate = (dateStr: string) =>
  new Date(dateStr).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' })

export default function DocumentOriginal({ documentId, onBack }: Props) {
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

  // rows:1짜리는 OCR이 일반 텍스트를 표로 잘못 인식한 노이즈일 가능성이 높아서 제외
  // (오탐인 경우 이 필터를 빼면 전부 표시됨)
  const realTables = (doc?.raw?.tables ?? []).filter(t => t.rows > 1)

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
        <div className="flex items-center gap-2">
          <FileText size={15} className="text-gray-400" />
          <h1 className="text-sm font-medium text-gray-700 dark:text-gray-200">
            {doc?.filename ?? '불러오는 중...'}
          </h1>
        </div>
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
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-400">
            원본 파일
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-8 min-h-[400px]">
          {loading ? (
            <p className="text-sm text-gray-400 text-center py-12">불러오는 중...</p>
          ) : notFound || !doc ? (
            <p className="text-sm text-gray-400 text-center py-12">문서를 찾을 수 없어요.</p>
          ) : (
            <>
              <div className="flex items-center gap-3 mb-6 pb-4 border-b border-gray-100 dark:border-gray-700">
                <div className="w-10 h-10 rounded-xl bg-red-50 dark:bg-red-900/30 flex items-center justify-center">
                  <File size={18} className="text-red-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{doc.filename}</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">{formatDate(doc.created_at)}</p>
                </div>
              </div>
              <pre className="text-sm text-gray-700 dark:text-gray-300 leading-7 whitespace-pre-wrap font-sans">
                {doc.raw?.original_text || '원문 내용이 없어요.'}
              </pre>
            </>
          )}
        </div>

        {/* 표 영역 — 실제 표(rows > 1)가 있을 때만 표시 */}
        {!loading && doc && realTables.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-6">
            <div className="flex items-center gap-2 mb-4">
              <Table2 size={15} className="text-gray-400" />
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                추출된 표 ({realTables.length}개)
              </p>
            </div>
            <div className="flex flex-col gap-6">
              {realTables.map((table, i) => (
                <div key={i} className="overflow-x-auto">
                  <div className="prose prose-sm dark:prose-invert max-w-none
                    [&_table]:w-full [&_table]:border [&_table]:border-gray-200 dark:[&_table]:border-gray-700
                    [&_th]:bg-gray-50 dark:[&_th]:bg-gray-700 [&_th]:text-xs [&_th]:font-medium [&_th]:text-gray-500 dark:[&_th]:text-gray-300 [&_th]:p-2 [&_th]:border [&_th]:border-gray-200 dark:[&_th]:border-gray-700
                    [&_td]:text-xs [&_td]:text-gray-700 dark:[&_td]:text-gray-200 [&_td]:p-2 [&_td]:border [&_td]:border-gray-100 dark:[&_td]:border-gray-700">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{table.markdown}</ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}