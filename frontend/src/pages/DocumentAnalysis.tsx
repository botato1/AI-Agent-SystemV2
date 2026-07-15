// 문서 분석 결과 페이지
import { Document, Packer, Paragraph, TextRun, HeadingLevel } from 'docx'
import { saveAs } from 'file-saver'
import { jsPDF } from 'jspdf'

import { NanumGothicBase64 } from '../fonts/NanumGothic'
import { useToast } from '../App'

import { useState } from 'react'

import { ArrowLeft, Download, Share2 } from 'lucide-react'

import TabSummary from '../components/DocumentAnalysis/TabSummary'
import TabOriginal from '../components/DocumentAnalysis/TabOriginal'
import ConfidenceBar from '../components/shared/ConfidenceBar'
import TabTasks from '../components/DocumentAnalysis/TabTasks'
import TabRelated from '../components/DocumentAnalysis/TabRelated'

const tabs = ['요약', '전체 문서', 'Task', '연관 문서']

interface AnalysisProps {
  analysisData?: any
  onReview: () => void
  onGoToChat?: () => void
  onBack?: () => void
}

export default function Analysis({ analysisData, onReview, onGoToChat, onBack }: AnalysisProps) {
  const { showToast } = useToast()
  const [activeTab, setActiveTab] = useState(0) //활성화 탭 기본은 요약 탭

  const buildSummaryPoints = () =>
  analysisData?.analysis?.summary
    ? analysisData.analysis.summary.split('\n').filter((s: string) => s.trim())
    : ['요약 데이터가 없습니다.']

  //PDF 다운로드 jsPDF+나눔고딕
const handleDownload = () => {
  const doc = new jsPDF()
  doc.addFileToVFS('NanumGothic.ttf', NanumGothicBase64)
  doc.addFont('NanumGothic.ttf', 'NanumGothic', 'normal')
  doc.setFont('NanumGothic')

  doc.setFontSize(18)
  doc.text(`${analysisData?.filename ?? '문서'} 분석 보고서`, 20, 20)

  doc.setFontSize(11)
  doc.text(
    `생성일: ${analysisData?.created_at ? new Date(analysisData.created_at).toLocaleDateString('ko-KR') : '-'}`,
    20, 33
  )
  doc.text(
    `페이지 수: ${analysisData?.analysis?.page_count ?? '-'}`,
    20, 41
  )

  let y = 53
  doc.setFontSize(13)
  doc.text('문서 요약', 20, y)
  y += 8
  doc.setFontSize(10)
  buildSummaryPoints().forEach((point: string) => {
    doc.text(`- ${point}`, 22, y)
    y += 7
  })

  doc.save(`${analysisData?.filename ?? '분석'}_분석보고서.pdf`)
}


 // DOCX 다운로드: docx 라이브러리로 Word 문서 생성
const handleDownloadDocx = async () => {
  const doc = new Document({
    sections: [{
      children: [
        new Paragraph({
          text: `${analysisData?.filename ?? '문서'} 분석 보고서`,
          heading: HeadingLevel.HEADING_1
        }),
        new Paragraph({
          children: [new TextRun({
            text: `생성일: ${analysisData?.created_at ? new Date(analysisData.created_at).toLocaleDateString('ko-KR') : '-'}`,
            size: 22
          })]
        }),
        new Paragraph({
          children: [new TextRun({
            text: `페이지 수: ${analysisData?.analysis?.page_count ?? '-'}`,
            size: 22
          })]
        }),
        new Paragraph({ text: '문서 요약', heading: HeadingLevel.HEADING_2 }),
        ...buildSummaryPoints().map((point: string) =>
          new Paragraph({ children: [new TextRun({ text: `• ${point}`, size: 20 })] })
        ),
      ]
    }]
  })
  const blob = await Packer.toBlob(doc)
  saveAs(blob, `${analysisData?.filename ?? '분석'}_분석보고서.docx`)
}

//TXT 다운로드
const handleDownloadTxt = () => {
  const content = [
    `${analysisData?.filename ?? '문서'} 분석 보고서`,
    `생성일: ${analysisData?.created_at ? new Date(analysisData.created_at).toLocaleDateString('ko-KR') : '-'}`,
    `페이지 수: ${analysisData?.analysis?.page_count ?? '-'}`,
    '',
    '문서 요약',
    ...buildSummaryPoints().map((p: string) => `- ${p}`),
  ].join('\n')
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  saveAs(blob, `${analysisData?.filename ?? '분석'}_분석보고서.txt`)
}

  //공유 (현재 페이지 url 복사)
  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href)
    showToast('링크가 복사됐어요')
  }

  //activeTab 인덱스에 따라 탭 컴포넌트 변경
const renderTab = () => {
  switch (activeTab) {
    case 0: return <TabSummary analysisData={analysisData}/>
    case 1: return <TabOriginal analysisData={analysisData}/>
    case 2: return <TabTasks analysisData={analysisData}/>
    case 3: return <TabRelated />
    default: return <TabSummary />
  }
}

  return (
    <div id="analysis-content">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <ArrowLeft size={16} className="text-gray-500 dark:text-gray-400" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-gray-800 dark:text-white">
                {analysisData?.filename ?? '제목 없음'}
              </h1>
              <span className="text-xs bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300 px-2 py-0.5 rounded-full font-medium">분석 완료</span>
              {analysisData?.chroma_status === 'failed' && (
                <span className="text-xs bg-red-50 dark:bg-red-900/30 text-red-400 px-2 py-0.5 rounded-full font-medium">AI 분석 실패</span>
              )}
              {analysisData?.chroma_status === 'pending' && (
                <span className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-400 px-2 py-0.5 rounded-full font-medium">분석 준비 중</span>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              {analysisData?.created_at
                ? new Date(analysisData.created_at).toLocaleDateString('ko-KR')
                : '-'}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={handleDownload} className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-600 px-3 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
            <Download size={13} /> PDF
          </button>
          <button onClick={handleDownloadDocx} className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-600 px-3 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
            <Download size={13} /> DOCX
          </button>
          <button onClick={handleDownloadTxt} className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-600 px-3 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
            <Download size={13} /> TXT
          </button>
          <button onClick={handleShare} className="flex items-center gap-1.5 text-xs text-white bg-blue-600 px-3 py-1.5 rounded-lg hover:bg-blue-700">
            <Share2 size={13} /> 공유하기
          </button>
          <button onClick={onGoToChat} className="flex items-center gap-1.5 text-xs text-white bg-green-600 px-3 py-1.5 rounded-lg hover:bg-green-700">
          채팅 →
          </button>
        </div>
      </div>
      {/*신뢰도 바 , 검토 버튼*/}
      <ConfidenceBar confidence={72} onReview={onReview} />

      <div className="flex gap-1 mb-6 border-b border-gray-100 dark:border-gray-700">
        {tabs.map((tab, i) => (
          <button
            key={i}
            onClick={() => setActiveTab(i)}
            //활성/비활성 탭
            className={`text-sm px-4 py-2 border-b-2 transition ${activeTab === i ? 'border-blue-600 text-blue-600 font-medium' : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'}`}
          >
            {tab}
          </button>
        ))}
      </div>
      {/*선택된 탭 렌더링*/ }
      {renderTab()}
    </div>
  )
}