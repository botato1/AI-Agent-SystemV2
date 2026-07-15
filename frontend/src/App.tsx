import { useState, useEffect, createContext, useContext } from 'react'
import Sidebar from './components/layout/Sidebar'

import Home from './pages/Home'
import Documents from './pages/Documents'
import DocumentAnalysis from './pages/DocumentAnalysis'
import Tasks from './pages/Tasks'
import Settings from './pages/Settings'
import Pipeline from './pages/Pipeline'
import Graph from './pages/Graph'
import Voice from './pages/Voice'
import VoiceAnalysis from './pages/VoiceAnalysis'
import type { PipelineStatus } from './pages/Pipeline'

const BASE_URL = import.meta.env.VITE_API_URL

type ToastType = 'success' | 'error' | 'info'
interface ToastContextType {
  showToast: (message: string, type?: ToastType) => void
}

interface SttResult {
  file_id: string
  duration: number
  segments: { speaker: string; start: number; end: number; text: string; user_edited: boolean }[]
  fileName: string
  chromaStatus: 'success' | 'pending' | 'failed'
  originalFileUrl: string | null
}

export const ToastContext = createContext<ToastContextType>({ showToast: () => {} })
export const useToast = () => useContext(ToastContext)

export default function App() {
  const [activePage, setActivePage] = useState('home')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [isDark, setIsDark] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: ToastType } | null>(null)

  const [selectedChatId, setSelectedChatId] = useState<number | null>(null)
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null)
  const [targetFilename, setTargetFilename] = useState<string | null>(null)
  const [targetDocumentId, setTargetDocumentId] = useState<string | null>(null)

  const [reviewFileName, setReviewFileName] = useState<string | null>(null)
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0)

  const [voicePage, setVoicePage] = useState<'list' | 'result'>('list')
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null)
  const [sttResult, setSttResult] = useState<SttResult | null>(null)

  const [docViewMode, setDocViewMode] = useState<'list' | 'original' | 'analysis'>('list')
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)

  const [documentAnalysisData, setDocumentAnalysisData] = useState<any>(null)

  // 사이드바 배너용 업로드 중인 파일명 (null이면 배너 숨김)
  const [uploadingFile, setUploadingFile] = useState<string | null>(null)

  // 문서분석(Pipeline) 진행 상태 — 다른 페이지 갔다 와도 안 사라지게 App.tsx로 끌어올림
  const [pipelineFile, setPipelineFile] = useState<string | null>(null)
  const [pipelineStatuses, setPipelineStatuses] = useState<PipelineStatus[]>(Array(6).fill('wait'))
  const [pipelineCurrentStep, setPipelineCurrentStep] = useState(-1)
  const [pipelineLogs, setPipelineLogs] = useState<string[]>([])
  const [pipelineIsRunning, setPipelineIsRunning] = useState(false)
  const [pipelineUploadError, setPipelineUploadError] = useState<string | null>(null)

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [isDark])

  const showToast = (message: string, type: ToastType = 'info') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 1500)
  }

  // documentId로 문서 상세조회(GET /api/documents/{id})를 호출해서
  // analysis/organized가 채워진 진짜 데이터로 documentAnalysisData를 갱신함
  // - 업로드 직후(onFileUploaded)와 그래프/보관함에서 분석 보기 누를 때 둘 다 이 함수를 재사용
  const fetchDocumentAnalysis = async (documentId: string, fallbackChromaStatus?: string) => {
    try {
      const res = await fetch(`${BASE_URL}/api/documents/${documentId}`)
      const data = await res.json()
      if (data.status === 'success') {
        setDocumentAnalysisData({
          ...data.document,
          // 상세조회 응답엔 chroma_status가 없을 수 있어서, 업로드 응답값을 fallback으로 유지
          chroma_status: fallbackChromaStatus ?? data.document.chroma_status,
        })
      } else {
        setDocumentAnalysisData({ document_id: documentId })
      }
    } catch (err) {
      console.error('문서 상세조회 실패:', err)
      setDocumentAnalysisData({ document_id: documentId })
    }
  }

  const renderPage = () => {
    switch (activePage) {
      case 'home': return (
        <Home
          selectedChatId={selectedChatId}
          onRoomCreated={() => setSidebarRefreshKey(prev => prev + 1)}
          onSelectRoom={(room_id) => setActiveRoomId(room_id)}
          activeRoomId={activeRoomId}
          setActiveRoomId={setActiveRoomId}
          targetFilename={targetFilename}
          targetDocumentId={targetDocumentId}
          onGoToAnalysis={(documentId) => {
            setDocumentAnalysisData(null) // 이동 전에 이전 데이터부터 비움
            if (documentId) {
              fetchDocumentAnalysis(documentId)
            }
            setActivePage('documentanalysis')
          }}
          onClearFilename={() => {
            setTargetFilename(null)
            setTargetDocumentId(null)
          }}
        />
      )
      case 'pipeline': return (
        <Pipeline
          onGoToAnalysis={() => setActivePage('documentanalysis')}
          reviewFileName={reviewFileName}
          onClearReview={() => setReviewFileName(null)}
          onFileUploaded={(filename, uploadData) => {
            console.log('파일명 세팅:', filename)
            setTargetFilename(filename)
            setTargetDocumentId(uploadData?.document_id ?? null)
            setDocumentAnalysisData(null)
            if (uploadData?.document_id) {
              fetchDocumentAnalysis(uploadData.document_id, uploadData.chroma_status)
            }
          }}
          onUploadStart={(filename) => setUploadingFile(filename)}
          onUploadEnd={() => setUploadingFile(null)}
          file={pipelineFile}
          setFile={setPipelineFile}
          statuses={pipelineStatuses}
          setStatuses={setPipelineStatuses}
          currentStep={pipelineCurrentStep}
          setCurrentStep={setPipelineCurrentStep}
          logs={pipelineLogs}
          setLogs={setPipelineLogs}
          isRunning={pipelineIsRunning}
          setIsRunning={setPipelineIsRunning}
          uploadError={pipelineUploadError}
          setUploadError={setPipelineUploadError}
        />
      )
      case 'documents': return (
        <Documents
          selectedDocId={selectedDocId}
          docViewMode={docViewMode}
          onNameClick={(id) => {
            setSelectedDocId(id)
            setDocViewMode('original')
          }}
          onAnalysisClick={(id) => {
            setSelectedDocId(id)
            setDocViewMode('analysis')
          }}
          onBack={() => setDocViewMode('list')}
        />
      )
      case 'documentanalysis': return (
        <DocumentAnalysis
          analysisData={documentAnalysisData}
          onReview={() => {
            setReviewFileName('마케팅 전략 회의.pdf')
            setActivePage('home')
            setTimeout(() => setActivePage('pipeline'), 0)
          }}
          onGoToChat={() => {
            // 이제 채팅방을 미리 만들어두지 않으므로, 새 채팅 상태로 보냄.
            // ChatArea가 targetDocumentId를 보고 이 문서를 칩으로 미리 보여주고,
            // 첫 메시지를 보내는 시점에 새로 생성되는 room에 연결됨
            setActiveRoomId(null)
            setActivePage('home')
          }}
          onBack={() => setActivePage('pipeline')}
        />
      )
      case 'tasks': return <Tasks />
      case 'settings': return <Settings />
      case 'graph': return (
        <Graph
          onGoToAnalysis={(documentId) => {
            setSelectedDocId(documentId)
            setDocViewMode('analysis')
            setActivePage('documents')
          }}
        />
      )
      case 'voice': return voicePage === 'result'
        ? <VoiceAnalysis
            fileId={selectedVoiceId!}
            sttResult={sttResult}
            onBack={() => setVoicePage('list')}
          />
        : <Voice
            onAnalyze={(id, result) => {
              setSelectedVoiceId(id)
              setSttResult(result)
              setVoicePage('result')
            }}
            onUploadStart={(filename) => setUploadingFile(filename)}
            onUploadEnd={() => setUploadingFile(null)}
          />
    }
  }

  return (
    <ToastContext.Provider value={{ showToast }}>
      <div className="bg-gray-50 dark:bg-[#1c1a1a] min-h-screen flex transition-colors duration-300">
        <Sidebar
          refreshKey={sidebarRefreshKey}
          activePage={activePage}
          onPageChange={setActivePage}
          isDark={isDark}
          onToggleDark={() => setIsDark(!isDark)}
          onChatSelect={(id) => {
            setSelectedChatId(id)
            setActivePage('home')
          }}
          onCollapse={(v) => setSidebarCollapsed(v)}
          onRoomSelect={(room_id, filename, documentId) => {
            setActiveRoomId(room_id)
            setTargetFilename(filename ?? null)
            setTargetDocumentId(documentId ?? null)
            setActivePage('home')
          }}
          uploadingFile={uploadingFile}
        />
        <main className={`${sidebarCollapsed ? 'ml-14' : 'ml-52'} flex-1 p-6 transition-all duration-300`}>
          {renderPage()}
        </main>

        {toast && (
          <div className={`fixed top-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-medium border transition-all
            bg-[#f0faf4] dark:bg-[#2a2a2a] border-[#c8e6d0] dark:border-[#3a3a3a] text-gray-800 dark:text-white`}>
            {toast.type === 'success' && (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            )}
            {toast.type === 'error' && (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            )}
            {toast.type === 'info' && (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2.5">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            )}
            {toast.message}
          </div>
        )}
      </div>
    </ToastContext.Provider>
  )
}