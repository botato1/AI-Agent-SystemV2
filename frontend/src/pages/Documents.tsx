import { useState } from 'react'
import DocumentTab from '../components/Documents/DocumentTab'
import VoiceTab from '../components/Documents/VoiceTab'
import DocumentOriginal from '../components/Documents/DocumentOriginal'
import DocumentAnalysis from '../components/Documents/DocumentAnalysis'
import VoiceAnalysis from './VoiceAnalysis' // 음성 분석 페이지 재사용 (documentId만 넘기면 자체 재조회함)

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

  // 음성 분석 보기는 문서 쪽(docViewMode)과 별개로 관리.
  // DocumentOriginal/DocumentAnalysis가 documentId만 받아서 자체 fetch하는 패턴을 그대로 따라감
  const [voiceViewMode, setVoiceViewMode] = useState<'list' | 'analysis'>('list')
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null)

  if (docViewMode === 'original' && selectedDocId) {
    return <DocumentOriginal documentId={selectedDocId} onBack={onBack} />
  }
  if (docViewMode === 'analysis' && selectedDocId) {
    return <DocumentAnalysis documentId={selectedDocId} onBack={onBack} />
  }

  if (voiceViewMode === 'analysis' && selectedVoiceId) {
    return (
      <VoiceAnalysis
        fileId={selectedVoiceId}
        sttResult={null} // 보관함에서 들어온 거라 항상 GET /api/stt/{id}로 새로 조회
        onBack={() => setVoiceViewMode('list')}
      />
    )
  }

  return (
    <div>
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
          onNameClick={(id) => console.log('음성 원본:', id)} // 음성 원본 보기는 아직 보류
          onAnalysisClick={(id) => {
            setSelectedVoiceId(id)
            setVoiceViewMode('analysis')
          }}
        />
      )}
    </div>
  )
}