import { useState, useEffect } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { Upload, FileText, CheckCircle, Circle, Loader, AlertCircle } from 'lucide-react'

const BASE_URL = import.meta.env.VITE_API_URL

const steps = [
  { id: 1, label: '입력 처리', desc: '음성/텍스트/PDF/이미지 분석', detail: 'Whisper STT · PyMuPDF · Tesseract OCR' },
  { id: 2, label: 'Agent 흐름 제어', desc: 'LangGraph 노드 분기 처리', detail: 'LangGraph · 입력 유형별 라우팅' },
  { id: 3, label: 'LLM 분석 및 요약', desc: '핵심 내용 요약 · 키워드 추출', detail: 'Qwen2.5 · 회의록 정리 · Task 추출' },
  { id: 4, label: 'RAG 검색', desc: '벡터 DB 검색 · 관련 문서 매칭', detail: 'Vector DB · 임베딩 · 유사도 검색' },
  { id: 5, label: '그래프 시각화', desc: '문서 연관성 노드 시각화', detail: '임베딩 유사도 · 노드/엣지 렌더링' },
]

export type PipelineStatus = 'wait' | 'running' | 'done' | 'error'

interface PipelineProps {
  onGoToAnalysis: () => void
  reviewFileName: string | null
  onClearReview: () => void
  onFileUploaded?: (filename: string, analysisData?: any) => void
  onUploadStart?: (filename: string) => void
  onUploadEnd?: () => void
  file: string | null
  setFile: Dispatch<SetStateAction<string | null>>
  statuses: PipelineStatus[]
  setStatuses: Dispatch<SetStateAction<PipelineStatus[]>>
  currentStep: number
  setCurrentStep: Dispatch<SetStateAction<number>>
  logs: string[]
  setLogs: Dispatch<SetStateAction<string[]>>
  isRunning: boolean
  setIsRunning: Dispatch<SetStateAction<boolean>>
  uploadError: string | null
  setUploadError: Dispatch<SetStateAction<string | null>>
}

export default function Pipeline({
  onGoToAnalysis, reviewFileName, onClearReview, onFileUploaded, onUploadStart, onUploadEnd,
  file, setFile, statuses, setStatuses, currentStep, setCurrentStep, logs, setLogs, isRunning, setIsRunning, uploadError, setUploadError,
}: PipelineProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [prompt, setPrompt] = useState('')

  const addLog = (msg: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`])
  }

  // 업로드만 함 — 채팅방은 더 이상 자동으로 생성하지 않음.
  // 문서는 채팅 화면의 + 버튼으로 나중에 원하는 채팅방에 선택해서 연결함
  const startPipeline = async (selectedFile: File) => {
    onUploadStart?.(selectedFile.name)
    setFile(selectedFile.name)
    setStatuses(Array(steps.length).fill('wait'))
    setLogs([])
    setUploadError(null)
    setIsRunning(true)

    addLog('문서 업로드 중...')
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('type', 'document')
      formData.append('room_id', '') 

      const uploadRes = await fetch(`${BASE_URL}/api/documents/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!uploadRes.ok) throw new Error('문서 업로드 실패')
      const uploadData = await uploadRes.json()
      if (uploadData.status === 'error') throw new Error(uploadData.error ?? '문서 처리 실패')

      console.log('업로드 응답:', uploadData)
      addLog(`문서 처리 완료: ${uploadData.filename}`)
      addLog('메타데이터 저장 완료 ✓')

      onFileUploaded?.(uploadData.filename, uploadData)

      setCurrentStep(0)

    } catch (err: any) {
      console.error('업로드 오류:', err)
      setUploadError(err.message)
      addLog(`오류: ${err.message}`)
      setIsRunning(false)
      onUploadEnd?.()
    }
  }
useEffect(() => {
  if (currentStep < 0 || currentStep >= steps.length) {
    if (currentStep === steps.length) {
      setIsRunning(false)
      onUploadEnd?.()
      if (Notification.permission === 'granted') {
        new Notification('문서 분석 완료', {
          body: `${file} 분석이 완료됐어요!`,
        })
      }
    }
    return
  }
  const step = steps[currentStep]
  if (!step) return // 혹시 모를 범위 밖 값 방어

  setStatuses(prev => {
    const next = [...prev]
    next[currentStep] = 'running'
    return next
  })
  addLog(`${step.label} 시작...`)
  const timer = setTimeout(() => {
    setStatuses(prev => {
      const next = [...prev]
      next[currentStep] = 'done'
      return next
    })
    addLog(`${step.label} 완료 ✓`)
    setCurrentStep(prev => prev + 1)
  }, 1500)
  return () => clearTimeout(timer)
}, [currentStep])
  useEffect(() => {
    if (reviewFileName) {
      addLog(`재검토 요청: ${reviewFileName}`)
      setFile(reviewFileName)
      setStatuses(Array(steps.length).fill('wait'))
      setLogs([])
      setCurrentStep(0)
      setIsRunning(true)
    }
  }, [reviewFileName])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) startPipeline(droppedFile)
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (selected) startPipeline(selected)
  }

  const reset = () => {
    setFile(null)
    setStatuses(Array(steps.length).fill('wait'))
    setCurrentStep(-1)
    setLogs([])
    setIsRunning(false)
    setUploadError(null)
    onClearReview()
  }

  const getIcon = (status: PipelineStatus) => {
    if (status === 'done') return <CheckCircle size={18} className="text-blue-500" />
    if (status === 'running') return <Loader size={18} className="text-blue-500 animate-spin" />
    if (status === 'error') return <AlertCircle size={18} className="text-red-400" />
    return <Circle size={18} className="text-gray-300 dark:text-gray-600" />
  }

  const doneCount = statuses.filter(s => s === 'done').length

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-bold text-gray-800 dark:text-white">문서 분석</h1>
          <p className="text-xs text-gray-400 mt-1">파일을 업로드하면 AI Agent가 자동으로 처리해요</p>
        </div>
        {file && (
          <button onClick={reset} className="text-xs text-gray-400 border border-gray-200 dark:border-gray-600 px-3 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
            초기화
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="flex flex-col gap-4">

          {reviewFileName && !file && (
            <div className="flex items-center justify-between bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-xl px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">🔄 재검토 중</span>
                <span className="text-xs text-amber-500 dark:text-amber-300">{reviewFileName}</span>
              </div>
              <button onClick={onClearReview} className="text-xs text-amber-400 hover:text-amber-600">취소</button>
            </div>
          )}

          {uploadError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-xl px-4 py-3">
              <p className="text-xs text-red-500">❌ {uploadError}</p>
            </div>
          )}

          {!file ? (
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-2xl p-10 flex flex-col items-center justify-center transition ${
                isDragging
                  ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800'
              }`}
            >
              <div className="w-14 h-14 bg-blue-50 dark:bg-blue-900/30 rounded-2xl flex items-center justify-center mb-4">
                <Upload className="text-blue-400" size={24} />
              </div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">파일을 드래그하거나 클릭해서 업로드</p>
              <p className="text-xs text-gray-400 mb-4">PDF · DOCX · TXT · 이미지 지원</p>
              <label className="bg-blue-600 text-white text-xs px-4 py-2 rounded-lg cursor-pointer hover:bg-blue-700">
                파일 선택
                <input type="file" className="hidden" onChange={handleFileInput} accept=".pdf,.docx,.txt,.png,.jpg" />
              </label>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-9 h-9 bg-blue-50 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
                  <FileText size={16} className="text-blue-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{file}</p>
                  <p className="text-xs text-gray-400">{isRunning ? `${doneCount}/${steps.length} 단계 처리 중...` : '처리 완료 ✓'}</p>
                </div>
              </div>
              <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 mb-1">
                <div className="bg-blue-500 h-1.5 rounded-full transition-all duration-500" style={{ width: `${(doneCount / steps.length) * 100}%` }} />
              </div>
              <p className="text-xs text-gray-400 text-right">{Math.round((doneCount / steps.length) * 100)}%</p>
            </div>
          )}

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-600 p-4">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">분석 요청사항</h3>
            <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
              AI가 분석 시 참고할 내용을 입력해주세요
            </p>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="예) 할 일과 담당자 위주로 정리해줘"
              className="w-full resize-none text-sm bg-gray-100 dark:bg-[#161616] border border-gray-200 dark:border-gray-700 rounded-lg p-3 text-gray-700 dark:text-gray-300 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-400 min-h-[100px]"
            />
            <div className="flex justify-end gap-2 mt-3">
              <button onClick={() => setPrompt('')} className="px-4 py-1.5 text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                초기화
              </button>
              <button className="px-4 py-1.5 text-xs text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors">
                저장
              </button>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
            <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-4 uppercase tracking-wider">처리 단계</h3>
            <div className="flex flex-col">
              {steps.map((step, i) => (
                <div key={step.id} className="flex gap-3 relative">
                  {i < steps.length - 1 && (
                    <div className={`absolute left-[9px] top-6 w-0.5 h-8 ${statuses[i] === 'done' ? 'bg-blue-200 dark:bg-blue-800' : 'bg-gray-100 dark:bg-gray-700'}`} />
                  )}
                  <div className="flex-shrink-0 mt-1">{getIcon(statuses[i])}</div>
                  <div className={`flex-1 pb-6 ${i === steps.length - 1 ? 'pb-0' : ''}`}>
                    <div className="flex items-center justify-between">
                      <p className={`text-sm font-medium ${statuses[i] === 'done' ? 'text-gray-700 dark:text-gray-200' : statuses[i] === 'running' ? 'text-blue-600' : 'text-gray-300 dark:text-gray-600'}`}>
                        {step.label}
                      </p>
                      {statuses[i] === 'running' && <span className="text-xs text-blue-500 bg-blue-50 dark:bg-blue-900/30 px-2 py-0.5 rounded-full">처리 중</span>}
                      {statuses[i] === 'done' && <span className="text-xs text-green-500 bg-green-50 dark:bg-green-900/30 px-2 py-0.5 rounded-full">완료</span>}
                    </div>
                    <p className={`text-xs mt-0.5 ${statuses[i] !== 'wait' ? 'text-gray-400' : 'text-gray-200 dark:text-gray-700'}`}>{step.desc}</p>
                    {statuses[i] !== 'wait' && <p className="text-xs text-gray-300 dark:text-gray-600 mt-0.5">{step.detail}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-gray-900 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-3 h-3 rounded-full bg-red-400" />
              <div className="w-3 h-3 rounded-full bg-yellow-400" />
              <div className="w-3 h-3 rounded-full bg-green-400" />
              <span className="text-xs text-gray-500 ml-2">Agent 실행 로그</span>
            </div>
            <div className="flex flex-col gap-1.5 overflow-y-auto transition-all duration-300"
              style={{ minHeight: '500px', maxHeight: '320px', height: logs.length === 0 ? '40px' : `${Math.min(logs.length * 24 + 16, 320)}px` }}>
              {logs.length === 0 ? (
                <p className="text-xs text-gray-600">파일을 업로드하면 로그가 표시됩니다...</p>
              ) : (
                logs.map((log, i) => (
                  <p key={i} className={`text-xs font-mono ${log.includes('완료') ? 'text-green-400' : log.includes('오류') ? 'text-red-400' : 'text-gray-300'}`}>
                    {log}
                  </p>
                ))
              )}
            </div>
          </div>

          {doneCount === steps.length && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-blue-100 dark:border-blue-800 p-4">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">✅ 처리 완료</h3>
              <button
                onClick={onGoToAnalysis}
                className="w-full text-xs text-white bg-blue-600 px-3 py-2 rounded-lg hover:bg-blue-700"
              >
                결과 보러가기 →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}