import { useState, useEffect } from 'react'
import { Search, Grid, List, Mic, Clock, AlertTriangle } from 'lucide-react'

const BASE_URL = import.meta.env.VITE_API_URL
const FILTERS = ['전체', 'WAV', 'MP3', 'M4A'] as const

interface VoiceItem {
  document_id: string
  filename: string
  duration_sec: number
  chroma_status: 'success' | 'pending' | 'failed'
  created_at: string
}

type Props = {
  onNameClick: (id: string) => void
  onAnalysisClick: (id: string) => void
}

const typeColors: Record<string, string> = {
  WAV: 'text-[#818cf8]',
  MP3: 'text-[#34d399]',
  M4A: 'text-[#fb923c]',
}

const getExt = (filename: string) => filename.split('.').pop()?.toUpperCase() ?? ''

const formatDate = (dateStr: string) =>
  new Date(dateStr).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' })

const formatDuration = (sec: number) => {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

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

export default function VoiceTab({ onNameClick, onAnalysisClick }: Props) {
  const [search, setSearch] = useState('')
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const [filter, setFilter] = useState('전체')
  const [voices, setVoices] = useState<VoiceItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${BASE_URL}/api/stt/list`)
      .then(r => r.json())
      .then(data => {
        setVoices(data.data ?? [])
      })
      .catch(err => console.error('음성 목록 불러오기 실패:', err))
      .finally(() => setLoading(false))
  }, [])

  const filtered = voices.filter((v) => {
    const matchSearch = v.filename.toLowerCase().includes(search.toLowerCase())
    const matchFilter = filter === '전체' || getExt(v.filename) === filter
    return matchSearch && matchFilter
  })

  return (
    <div>
      <div className="flex items-center gap-3 mb-5">
        <div className="flex-1 flex items-center gap-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2">
          <Search size={14} className="text-gray-300" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="파일 검색..."
            className="flex-1 text-sm text-gray-700 dark:text-gray-200 outline-none placeholder-gray-500 bg-transparent"
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
          <p className="text-sm text-gray-400">음성 파일이 없어요</p>
        </div>
      ) : viewMode === 'list' ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 overflow-hidden">
          <div className="grid grid-cols-12 px-4 py-2 border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700">
            <span className="col-span-4 text-xs text-gray-400 dark:text-gray-500 font-medium">이름</span>
            <span className="col-span-2 text-xs text-gray-400 dark:text-gray-500 font-medium">유형</span>
            <span className="col-span-2 text-xs text-gray-400 dark:text-gray-500 font-medium">업로드 날짜</span>
            <span className="col-span-2 text-xs text-gray-400 dark:text-gray-500 font-medium">크기</span>
            <span className="col-span-1 text-xs text-gray-400 dark:text-gray-500 font-medium">길이</span>
            <span className="col-span-1 text-xs text-gray-400 dark:text-gray-500 font-medium">분석</span>
          </div>
          {filtered.map((voice) => (
            <div key={voice.document_id} className="grid grid-cols-12 px-4 py-3 border-b border-gray-50 dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700 transition items-center">
              <div className="col-span-4 flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center border border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500 flex-shrink-0">
                  <Mic size={16} />
                </div>
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <button
                    onClick={() => onNameClick(voice.document_id)}
                    className="text-sm text-gray-700 dark:text-gray-200 truncate hover:text-blue-600 hover:underline text-left min-w-0"
                  >
                    {voice.filename}
                  </button>
                  <ChromaStatusBadge status={voice.chroma_status} />
                </div>
              </div>
              <div className="col-span-2">
                <span className={`text-xs font-medium ${typeColors[getExt(voice.filename)] ?? 'text-gray-400'}`}>
                  {getExt(voice.filename)}
                </span>
              </div>
              <span className="col-span-2 text-xs text-gray-400 dark:text-gray-500">{formatDate(voice.created_at)}</span>
              <span className="col-span-2 text-xs text-gray-400 dark:text-gray-500">-</span>
              <span className="col-span-1 text-xs text-gray-400 dark:text-gray-500">{formatDuration(voice.duration_sec)}</span>
              <div className="col-span-1">
                <button onClick={() => onAnalysisClick(voice.document_id)} className="text-xs text-blue-500 hover:underline">분석</button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {filtered.map((voice) => (
            <div key={voice.document_id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4 hover:border-blue-200 dark:hover:border-blue-700 transition">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-3 border border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500">
                <Mic size={18} />
              </div>
              <div className="flex items-center gap-1.5 mb-1">
                <button
                  onClick={() => onNameClick(voice.document_id)}
                  className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate text-left hover:text-blue-600 hover:underline min-w-0 flex-1"
                >
                  {voice.filename}
                </button>
                <ChromaStatusBadge status={voice.chroma_status} />
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className={`text-xs font-medium ${typeColors[getExt(voice.filename)] ?? 'text-gray-400'}`}>
                  {getExt(voice.filename)}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500">{formatDuration(voice.duration_sec)}</span>
              </div>
              <div className="flex items-center justify-between mt-2">
                <p className="text-xs text-gray-300 dark:text-gray-600">{formatDate(voice.created_at)}</p>
                <button onClick={() => onAnalysisClick(voice.document_id)} className="text-xs text-blue-500 hover:underline">분석</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}