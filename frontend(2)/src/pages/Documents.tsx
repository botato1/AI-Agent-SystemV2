import { useState } from 'react'
import DocumentTab from '../components/Documents/DocumentTab'
import VoiceTab from '../components/Documents/VoiceTab'
import DocumentOriginal from '../components/Documents/DocumentOriginal'
import DocumentAnalysis from '../components/Documents/DocumentAnalysis'
import VoiceAnalysis from './VoiceAnalysis'

interface SttResult {
  file_id: string
  duration: number
  segments: any[]
  fileName: string
  chromaStatus: 'success' | 'pending' | 'failed'
  originalFileUrl: string | null
}

type Props = {
  selectedDocId: string | null
  docViewMode: 'list' | 'original' | 'analysis'
  onNameClick: (id: string) => void
  onAnalysisClick: (id: string) => void
  onBack: () => void
}

const tabs = ['문서', '음성']

export default function Documents({ selectedDocId, docViewMode, onNameClick, onAnalysisClick, onBack }: Props) {
  const [activeTab, setActiveTab] = useState(0)
  const [voiceViewMode, setVoiceViewMode] = useState<'list' | 'analysis'>('list')
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null)

  // 문서 원본 보기
  if (docViewMode === 'original' && selectedDocId) {
    return <DocumentOriginal documentId={selectedDocId} onBack={onBack} />
  }
  // 문서 분석 보기
  if (docViewMode === 'analysis' && selectedDocId) {
    return <DocumentAnalysis documentId={selectedDocId} onBack={onBack} />
  }
  // 음성 분석 보기
  if (voiceViewMode === 'analysis' && selectedVoiceId) {
    return (
      <VoiceAnalysis
        fileId={selectedVoiceId}
        sttResult={null}
        onBack={() => setVoiceViewMode('list')}
      />
    )
  }

  return (
    <div className="p-6" style={{ height: '100vh', overflowY: 'auto' }}>
      <div className="mb-5">
        <h1 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          문서 보관함
        </h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          업로드한 문서와 음성 파일을 관리하세요
        </p>
      </div>

      {/* 문서 / 음성 탭 */}
      <div className="flex gap-1 mb-5 border-b border-gray-100 dark:border-gray-700">
        {tabs.map((tab, i) => (
          <button
            key={i}
            onClick={() => setActiveTab(i)}
            className={`text-sm px-4 py-2 border-b-2 transition ${
              activeTab === i
                ? 'border-blue-600 text-blue-600 font-medium'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === 0 && (
        <DocumentTab
          onNameClick={onNameClick}
          onAnalysisClick={onAnalysisClick}
        />
      )}
      {activeTab === 1 && (
        <VoiceTab
          onNameClick={(id) => console.log('음성 원본:', id)}
          onAnalysisClick={(id) => {
            setSelectedVoiceId(id)
            setVoiceViewMode('analysis')
          }}
        />
      )}
    </div>
  )
}