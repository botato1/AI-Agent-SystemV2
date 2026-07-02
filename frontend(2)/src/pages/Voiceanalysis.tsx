import { useState, useEffect, useRef } from 'react'
import { Clock, AlertTriangle } from 'lucide-react'
import { useToast } from '../App'
import TabSummary from '../components/VoiceAnalysis/TabSummary'
import TabScript from '../components/VoiceAnalysis/TabScript'
import TabKeyword from '../components/VoiceAnalysis/TabKeyword'
import TabTasks from '../components/VoiceAnalysis/TabTasks'
import TabSpeakers from '../components/VoiceAnalysis/TabSpeakers'

const BASE_URL = import.meta.env.VITE_API_URL
const TABS = ['요약', '전체 스크립트', '키워드', '액션 아이템'] as const
type Tab = typeof TABS[number]

interface SttSegment {
  speaker: string
  start: number
  end: number
  text: string
  user_edited: boolean
}

interface SttResult {
  file_id: string
  duration: number
  segments: SttSegment[]
  fileName: string
  chromaStatus: 'success' | 'pending' | 'failed'
  originalFileUrl: string | null
}

interface Props {
  fileId: string
  sttResult: SttResult | null
  onBack: () => void
}

interface ResolvedVoice {
  fileName: string
  duration: number
  segments: SttSegment[]
  chromaStatus?: 'success' | 'pending' | 'failed'
  originalFileUrl: string | null
}

const formatDuration = (seconds: number) => {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0')
  const s = Math.floor(seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

function ChromaStatusBadge({ status }: { status?: string }) {
  if (status === 'pending') {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-400 flex items-center gap-1 flex-shrink-0">
        <Clock size={11} /> AI 분석 준비 중
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full bg-red-50 dark:bg-red-900/30 text-red-400 flex items-center gap-1 flex-shrink-0">
        <AlertTriangle size={11} /> AI 분석 기능 일시 중단
      </span>
    )
  }
  return null
}

export default function VoiceAnalysis({ fileId, sttResult, onBack }: Props) {
  const { showToast } = useToast()
  const [activeTab, setActiveTab] = useState<Tab>('요약')
  const [fetched, setFetched] = useState<ResolvedVoice | null>(null)
  const [loading, setLoading] = useState(false)

  const audioRef = useRef<HTMLAudioElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1)

  useEffect(() => {
    if (sttResult) return
    setLoading(true)
    fetch(`${BASE_URL}/api/stt/${fileId}`)
      .then(r => r.json())
      .then(data => {
        if (data.status === 'success') {
          const d = data.data
          setFetched({
            fileName: d.filename,
            duration: d.metadata?.duration_sec ?? 0,
            segments: (d.transcription ?? []).map((t: any) => ({
              speaker: t.speaker, start: t.start, end: t.end,
              text: t.text, user_edited: t.user_edited,
            })),
            originalFileUrl: d.metadata?.original_file_url ?? null,
          })
        } else {
          showToast('음성 분석 결과를 불러오지 못했어요', 'error')
        }
      })
      .catch(() => showToast('음성 분석 결과를 불러오지 못했어요', 'error'))
      .finally(() => setLoading(false))
  }, [fileId, sttResult])

  const view: ResolvedVoice | null = sttResult
    ? {
        fileName: sttResult.fileName,
        duration: sttResult.duration,
        segments: sttResult.segments,
        chromaStatus: sttResult.chromaStatus,
        originalFileUrl: sttResult.originalFileUrl,
      }
    : fetched

  const handleDownloadOriginal = async () => {
    if (!view?.originalFileUrl) { showToast('다운로드 가능한 원본 파일이 없어요', 'error'); return }
    try {
      const res = await fetch(view.originalFileUrl)
      if (!res.ok) throw new Error('파일 응답 실패')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = view.fileName
      document.body.appendChild(a); a.click()
      document.body.removeChild(a); URL.revokeObjectURL(url)
    } catch { showToast('파일을 다운로드하지 못했어요', 'error') }
  }

  const togglePlay = () => {
    if (!audioRef.current) return
    isPlaying ? audioRef.current.pause() : audioRef.current.play()
  }

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!audioRef.current || !view) return
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    audioRef.current.currentTime = ratio * view.duration
  }

  const cycleSpeed = () => {
    const speeds = [1, 1.25, 1.5, 2, 0.75]
    const next = speeds[(speeds.indexOf(playbackRate) + 1) % speeds.length]
    setPlaybackRate(next)
    if (audioRef.current) audioRef.current.playbackRate = next
  }

  if (loading) return (
    <div className="p-6"><p className="text-sm text-gray-400">불러오는 중...</p></div>
  )

  if (!view) return (
    <div className="p-6">
      <button onClick={onBack} className="text-xs text-gray-400 hover:text-blue-500 mb-4">← 목록으로</button>
      <p className="text-sm text-gray-400">분석 데이터를 찾을 수 없어요.</p>
    </div>
  )

  const duration = formatDuration(view.duration)

  return (
    <div className="p-6 overflow-y-auto" style={{ height: '100vh' }}>
      <div className="flex items-center gap-2 text-xs text-gray-400 mb-4">
        <button onClick={onBack} className="hover:text-blue-500 transition-colors">음성 기록</button>
        <span>›</span>
        <span className="text-gray-600 dark:text-gray-300">분석 결과</span>
      </div>

      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-lg font-medium text-gray-900 dark:text-white">{view.fileName}</h1>
            <p className="text-xs text-gray-400 mt-1">{duration} · {view.segments.length}개 발화 구간</p>
          </div>
          <ChromaStatusBadge status={view.chromaStatus} />
        </div>
        <button
          onClick={handleDownloadOriginal}
          className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          원본 파일 다운로드
        </button>
      </div>

      {/* 오디오 플레이어 */}
      <div className="bg-gray-50 dark:bg-[#1c1a1a] border border-gray-200 dark:border-gray-700 rounded-xl px-5 py-3 flex items-center gap-4 mb-5">
        <audio
          ref={audioRef}
          src={view.originalFileUrl ?? undefined}
          onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
        />
        <button
          onClick={togglePlay}
          disabled={!view.originalFileUrl}
          className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0 disabled:opacity-40"
        >
          {isPlaying ? (
            <svg className="w-3.5 h-3.5 text-white" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="5" width="4" height="14" /><rect x="14" y="5" width="4" height="14" />
            </svg>
          ) : (
            <svg className="w-4 h-4 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>
        <span className="text-xs text-gray-500 dark:text-gray-400 w-24 flex-shrink-0">
          {formatDuration(currentTime)} / {duration}
        </span>
        <div onClick={handleSeek} className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-1 cursor-pointer">
          <div className="bg-blue-500 h-1 rounded-full" style={{ width: view.duration ? `${(currentTime / view.duration) * 100}%` : '0%' }} />
        </div>
        <button onClick={cycleSpeed} className="text-xs text-gray-400 flex-shrink-0 hover:text-gray-600">
          {playbackRate}x
        </button>
      </div>

      {/* 탭 */}
      <div className="flex gap-1 mb-4 border-b border-gray-100 dark:border-gray-700">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
              activeTab === tab
                ? 'text-blue-500 border-blue-500 font-medium'
                : 'text-gray-500 dark:text-gray-400 border-transparent hover:text-gray-700'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === '요약' && (
        <div className="flex gap-6">
          <div className="flex-1 min-w-0">
            <TabSummary duration={duration} segmentCount={view.segments.length} />
          </div>
          <div className="w-52 flex-shrink-0">
            <TabSpeakers segments={view.segments} />
          </div>
        </div>
      )}
      {activeTab === '전체 스크립트' && <TabScript segments={view.segments} />}
      {activeTab === '키워드' && <TabKeyword />}
      {activeTab === '액션 아이템' && <TabTasks />}
    </div>
  )
}