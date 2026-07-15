import { useState, useRef, useEffect } from 'react'
import { Clock, AlertTriangle } from 'lucide-react'
import { useToast } from '../App'

const BASE_URL = import.meta.env.VITE_API_URL

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

interface VoiceFile {
  id: string
  name: string
  duration: string
  size: string
  uploadDate: string
  sttResult: SttResult | null
  chromaStatus: 'success' | 'pending' | 'failed'
}

interface Props {
  onAnalyze: (fileId: string, sttResult: SttResult) => void
  onUploadStart?: (filename: string) => void
  onUploadEnd?: () => void
}

const formatDuration = (seconds: number) => {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0')
  const s = Math.floor(seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
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

export default function Voice({ onAnalyze, onUploadStart, onUploadEnd }: Props) {
  const [files, setFiles] = useState<VoiceFile[]>([])
  const [prompt, setPrompt] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { showToast } = useToast()

  useEffect(() => {
    fetch(`${BASE_URL}/api/stt/list`, { method: 'GET' })
      .then(r => r.json())
      .then(data => {
        if (data.status === 'success') {
          const loaded: VoiceFile[] = data.data.map((item: any) => ({
            id: item.document_id,
            name: item.filename ?? item.title,
            duration: item.duration_sec ?
              formatDuration(item.duration_sec) : '--:--',
            size: '--',
            uploadDate: new Date(item.created_at).toLocaleString('ko-KR', {
              year: 'numeric', month: '2-digit', day: '2-digit',
              hour: '2-digit', minute: '2-digit',
            }),
            sttResult: null,
            chromaStatus: item.chroma_status ?? 'success',
          }))
          setFiles(loaded)
        }
      })
      .catch(err => console.error('목록 불러오기 실패:', err))
  }, [])

  const handleUpload = async (selectedFile: File) => {
    setUploading(true)
    onUploadStart?.(selectedFile.name)
    setUploadError(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      if (prompt) formData.append('topic', prompt)

      const res = await fetch(`${BASE_URL}/api/stt/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error('STT 업로드 실패')
      const data = await res.json()
      console.log('STT 업로드 응답:', data)
      if (data.status !== 'success') throw new Error(data.error ?? '업로드 실패')

      const { document_id, filename, transcription, duration_sec, chroma_status } = data

      if (chroma_status === 'pending') {
        showToast('AI 분석 준비 중입니다', 'info')
      } else if (chroma_status === 'failed') {
        showToast('AI 분석 기능을 일시적으로 사용할 수 없습니다', 'error')
      }

      const sttResult: SttResult = {
        file_id: document_id,
        duration: duration_sec,
        segments: transcription ?? [],
        fileName: filename ?? selectedFile.name,
        chromaStatus: chroma_status ?? 'success',
        originalFileUrl: data.metadata?.original_file_url ?? null,   // ← 추가
      }

      const newFile: VoiceFile = {
        id: document_id,
        name: filename ?? selectedFile.name,
        duration: formatDuration(duration_sec),
        size: `${(selectedFile.size / 1024 / 1024).toFixed(1)}MB`,
        uploadDate: new Date().toLocaleString('ko-KR', {
          year: 'numeric', month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit',
        }),
        sttResult,
        chromaStatus: chroma_status ?? 'success',
      }

      setFiles(prev => [newFile, ...prev])
      onAnalyze(document_id, sttResult)

    } catch (err: any) {
      setUploadError(err.message)
    } finally {
      setUploading(false)
      onUploadEnd?.()
    }
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (selected) handleUpload(selected)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) handleUpload(dropped)
  }

  const handleDelete = async (file: VoiceFile) => {
    if (!confirm('파일을 삭제할까요?')) return
    try {
      await fetch(`${BASE_URL}/api/stt/${file.id}`, { method: 'DELETE' })
      setFiles(prev => prev.filter(f => f.id !== file.id))
    } catch (err) {
      console.error('삭제 실패:', err)
    }
  }

  const handleAnalyze = async (file: VoiceFile) => {
    if (file.sttResult) {
      onAnalyze(file.id, file.sttResult)
    } else {
      try {
        const res = await fetch(`${BASE_URL}/api/stt/${file.id}`, { method: 'GET' })
        const data = await res.json()
        if (data.status === 'success') {
          const sttResult: SttResult = {
            file_id: data.data.document_id,
            duration: data.data.duration_sec ?? data.data.metadata?.duration_sec,
            segments: data.data.transcription,
            fileName: data.data.filename ?? data.data.metadata?.original_filename ?? file.name,
            chromaStatus: data.data.chroma_status ?? 'success',
            originalFileUrl: data.data.metadata?.original_file_url ?? null,
          }
          setFiles(prev => prev.map(f => f.id === file.id ? { ...f, sttResult } : f))
          onAnalyze(file.id, sttResult)
        }
      } catch (err) {
        console.error('조회 실패:', err)
      }
    }
  }

  return (
    <div className="flex-1 p-8 overflow-y-auto bg-white dark:bg-[#161616]">
      <div className="mb-6">
        <h1 className="text-xl font-medium text-gray-900 dark:text-white">음성 파일 관리</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">음성 파일을 업로드하고 분석 결과를 확인하세요.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center transition-colors ${
            isDragging
              ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20'
              : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-[#1c1a1a]'
          }`}
        >
          <div className="w-14 h-14 rounded-full bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center mb-4">
            <svg className="w-7 h-7 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
          </div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
            {uploading ? '분석 중...' : '음성 파일을 드래그하거나 클릭하여 업로드'}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">MP3, WAV, M4A, AAC 파일 지원</p>
          {uploadError && <p className="text-xs text-red-500 mb-2">❌ {uploadError}</p>}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="px-5 py-2 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          >
            {uploading ? '분석 중...' : '파일 선택'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".mp3,.wav,.m4a,.aac"
            className="hidden"
            onChange={handleFileInput}
          />
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-3">ⓘ 실시간 녹음 기능은 지원하지 않습니다.</p>
        </div>

        <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-5 flex flex-col bg-white dark:bg-[#1c1a1a]">
          <h2 className="text-sm font-medium text-gray-800 dark:text-white mb-1">분석 요청사항</h2>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">AI가 집중해서 분석할 내용을 입력하세요</p>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="예) 할 일과 담당자 위주로 정리해줘"
            className="flex-1 resize-none text-sm bg-gray-50 dark:bg-[#161616] border border-gray-200 dark:border-gray-700 rounded-lg p-3 text-gray-700 dark:text-gray-300 placeholder-gray-300 dark:placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-400 min-h-[120px]"
          />
          <div className="flex justify-end gap-2 mt-3">
            <button onClick={() => setPrompt('')} className="px-4 py-1.5 text-xs text-gray-500 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800">초기화</button>
            <button className="px-4 py-1.5 text-xs text-white bg-blue-500 hover:bg-blue-600 rounded-lg">저장</button>
          </div>
        </div>
      </div>

      <div className="border border-gray-200 dark:border-gray-700 rounded-xl bg-white dark:bg-[#1c1a1a]">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-800 dark:text-white">업로드된 파일</span>
            <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 rounded-full">{files.length}개</span>
          </div>
        </div>

        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_160px] px-5 py-2 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
          <span>파일명</span>
          <span>길이</span>
          <span>크기</span>
          <span>업로드 날짜</span>
          <span>작업</span>
        </div>

        {files.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <p className="text-sm text-gray-400">업로드된 파일이 없어요</p>
            <p className="text-xs text-gray-300 dark:text-gray-600 mt-1">음성 파일을 업로드하면 여기에 표시됩니다</p>
          </div>
        ) : (
          files.map((file) => (
            <div key={file.id} className="grid grid-cols-[2fr_1fr_1fr_1fr_160px] items-center px-5 py-3.5 border-b border-gray-50 dark:border-gray-800 last:border-none hover:bg-gray-50 dark:hover:bg-gray-800/40 transition-colors">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                  </svg>
                </div>
                <p className="text-sm text-gray-800 dark:text-gray-200 font-medium truncate max-w-[160px]">{file.name}</p>
                <ChromaStatusBadge status={file.chromaStatus} />
              </div>
              <span className="text-sm text-gray-600 dark:text-gray-400">{file.duration}</span>
              <span className="text-sm text-gray-600 dark:text-gray-400">{file.size}</span>
              <span className="text-sm text-gray-600 dark:text-gray-400">{file.uploadDate}</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleAnalyze(file)}
                  className="px-4 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
                >
                  {file.sttResult ? '분석 결과 보기' : '분석하기'}
                </button>
                <button
                  onClick={() => handleDelete(file)}
                  className="w-7 h-7 flex items-center justify-center rounded-lg text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                  aria-label="삭제"
                >
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6l-1 14H6L5 6"/>
                    <path d="M10 11v6"/>
                    <path d="M14 11v6"/>
                    <path d="M9 6V4h6v2"/>
                  </svg>
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}