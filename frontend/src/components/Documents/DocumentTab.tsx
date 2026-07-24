import { useState, useEffect } from 'react'
import { Search, Grid, List, Trash2, Clock, AlertTriangle } from 'lucide-react'

const BASE_URL = import.meta.env.VITE_API_URL

interface DocumentItem {
  document_id: string
  filename: string
  room_id: string
  type: string
  chroma_status: 'success' | 'pending' | 'failed'  // AI 분석(검색) 가능 여부
  created_at: string
}

type Props = {
  onNameClick: (id: string) => void
  onAnalysisClick: (id: string) => void
}

const FILTERS = ['전체', 'PDF', 'DOCX', 'TXT'] as const

// pending/failed만 아이콘 표시, success는 아무것도 안 보여줌
function ChromaStatusBadge({ status }: { status: string }) {
  if (status === 'pending') {
    return (
      <span title="AI 분석 준비 중입니다" className="inline-flex flex-shrink-0">
        <Clock size={12} className="text-gray-400" />
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span title="AI 분석 기능을 일시적으로 사용할 수 없습니다" className="inline-flex flex-shrink-0">
        <AlertTriangle size={12} className="text-red-400" />
      </span>
    )
  }
  return null
}

export default function DocumentTab({ onNameClick, onAnalysisClick }: Props) {
  const [search, setSearch] = useState('')
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const [filter, setFilter] = useState('전체')
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${BASE_URL}/api/documents`)
      .then(r => r.json())
      .then(data => {
        const docs = data.documents ?? []
        const documentsOnly = docs.filter((doc: DocumentItem) => doc.type === 'document')
        const unique = documentsOnly.filter((doc: DocumentItem, index: number, self: DocumentItem[]) =>
          index === self.findIndex(d => d.filename === doc.filename)
        )
        // ⚠️ 테스트용 — 화면 확인 끝나면 이 4줄 지우고 setDocuments(unique)로 되돌리기
      const testDocs = unique.map((d: DocumentItem, i: number) => ({
        ...d,
        chroma_status: i === 0 ? 'pending' : i === 1 ? 'failed' : 'success'
      }))
      setDocuments(testDocs)

      // setDocuments(unique)  ← 테스트 끝나면 이 줄 다시 살리기
    })
    .catch(err => console.error('문서 목록 불러오기 실패:', err))
    .finally(() => setLoading(false))
}, [])

  const handleDelete = async (doc: DocumentItem) => {
    if (!confirm(`"${doc.filename}" 을 삭제할까요?`)) return
    if (deletingId) return

    setDeletingId(doc.document_id)

    try {
      const res = await fetch(`${BASE_URL}/api/documents/${doc.document_id}`, {
        method: 'DELETE',
      })
      const data = await res.json()

      if (data.status === 'success') {
        
        setDocuments(prev => prev.filter(d => d.document_id !== doc.document_id))
      } else if (data.status === 'partial_success') {
        setDocuments(prev => prev.filter(d => d.document_id !== doc.document_id))
        alert('문서는 삭제됐지만 일부 파일 정리에 실패했어요. (관리자 확인이 필요해요)')
      } else {
        alert(data.message ?? '문서 삭제에 실패했어요.')
      }
    } catch (err) {
      console.error('문서 삭제 실패:', err)
      alert('문서 삭제 중 오류가 발생했어요. 백엔드 연결을 확인해주세요.')
    } finally {
      setDeletingId(null)
    }
  }

  const filtered = documents.filter((doc) => {
    const matchSearch = doc.filename.toLowerCase().includes(search.toLowerCase())
    const ext = doc.filename.split('.').pop()?.toUpperCase() ?? ''
    const matchFilter = filter === '전체' || ext === filter
    return matchSearch && matchFilter
  })

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('ko-KR', {
      year: 'numeric', month: '2-digit', day: '2-digit'
    })
  }

  const getExt = (filename: string) => filename.split('.').pop()?.toUpperCase() ?? ''

  const extColors: Record<string, string> = {
    PDF: 'text-[#818cf8]',
    DOCX: 'text-[#34d399]',
    TXT: 'text-[#fb923c]',
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-5">
        <div className="flex-1 flex items-center gap-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2">
          <Search size={14} className="text-gray-300" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="파일 검색..."
            className="flex-1 text-sm text-gray-700 dark:text-gray-200 outline-none placeholder-gray-300 bg-transparent"
          />
        </div>

        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition ${
                filter === f
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white dark:bg-gray-800 text-gray-400 dark:text-gray-500 border-gray-200 dark:border-gray-600 hover:border-blue-300'
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        <div className="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
          <button
            onClick={() => setViewMode('list')}
            className={`p-1.5 rounded-md transition ${viewMode === 'list' ? 'bg-white dark:bg-gray-600 shadow-sm' : ''}`}
          >
            <List size={14} className={viewMode === 'list' ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400'} />
          </button>
          <button
            onClick={() => setViewMode('grid')}
            className={`p-1.5 rounded-md transition ${viewMode === 'grid' ? 'bg-white dark:bg-gray-600 shadow-sm' : ''}`}
          >
            <Grid size={14} className={viewMode === 'grid' ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400'} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-12 text-center">
          <p className="text-sm text-gray-400">불러오는 중...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-12 text-center">
          <p className="text-sm text-gray-400">문서가 없어요</p>
          <p className="text-xs text-gray-300 dark:text-gray-600 mt-1">파이프라인에서 문서를 업로드해보세요</p>
        </div>
      ) : viewMode === 'list' ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 overflow-hidden">
          <div className="grid grid-cols-12 px-4 py-2 border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700">
            <span className="col-span-5 text-xs text-gray-400 font-medium">이름</span>
            <span className="col-span-2 text-xs text-gray-400 font-medium">유형</span>
            <span className="col-span-3 text-xs text-gray-400 font-medium">업로드 날짜</span>
            <span className="col-span-2 text-xs text-gray-400 font-medium">작업</span>
          </div>
          {filtered.map((doc) => {
            const isDeleting = deletingId === doc.document_id
            return (
              <div key={doc.document_id} className="grid grid-cols-12 px-4 py-3 border-b border-gray-50 dark:border-gray-700 last:border-0 items-center hover:bg-gray-50 dark:hover:bg-gray-700 transition">
                <div className="col-span-5 flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center border border-gray-200 dark:border-gray-700 text-gray-400 flex-shrink-0">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div className="flex items-center gap-1.5 min-w-0 flex-1">
                    <button
                      onClick={() => onNameClick(doc.document_id)}
                      className="text-sm text-gray-700 dark:text-gray-200 truncate hover:text-blue-600 hover:underline text-left min-w-0"
                    >
                      {doc.filename}
                    </button>
                    <ChromaStatusBadge status={doc.chroma_status} />
                  </div>
                </div>
                <div className="col-span-2">
                  <span className={`text-xs font-medium ${extColors[getExt(doc.filename)] ?? 'text-gray-400'}`}>
                    {getExt(doc.filename)}
                  </span>
                </div>
                <span className="col-span-3 text-xs text-gray-500 dark:text-gray-400">{formatDate(doc.created_at)}</span>
                <div className="col-span-2 flex items-center gap-2">
                  <button onClick={() => onAnalysisClick(doc.document_id)} className="text-xs text-blue-500 hover:underline">분석</button>
                  <button
                    onClick={() => handleDelete(doc)}
                    disabled={isDeleting}
                    className="w-7 h-7 flex items-center justify-center rounded-lg text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    aria-label="삭제"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {filtered.map((doc) => {
            const isDeleting = deletingId === doc.document_id
            return (
              <div key={doc.document_id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-4 hover:border-blue-300 dark:hover:border-blue-600 transition">
                <div className="flex items-start justify-between mb-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center border border-gray-200 dark:border-gray-700 text-gray-400">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <button
                    onClick={() => handleDelete(doc)}
                    disabled={isDeleting}
                    className="w-7 h-7 flex items-center justify-center rounded-lg text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    aria-label="삭제"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                <div className="flex items-center gap-1.5 mb-1">
                  <button
                    onClick={() => onNameClick(doc.document_id)}
                    className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate text-left hover:text-blue-600 hover:underline min-w-0 flex-1"
                  >
                    {doc.filename}
                  </button>
                  <ChromaStatusBadge status={doc.chroma_status} />
                </div>
                <div className="flex items-center justify-between mt-1">
                  <span className={`text-xs font-medium ${extColors[getExt(doc.filename)] ?? 'text-gray-400'}`}>
                    {getExt(doc.filename)}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-2">
                  <p className="text-xs text-gray-400">{formatDate(doc.created_at)}</p>
                  <button onClick={() => onAnalysisClick(doc.document_id)} className="text-xs text-blue-500 hover:underline">분석</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}