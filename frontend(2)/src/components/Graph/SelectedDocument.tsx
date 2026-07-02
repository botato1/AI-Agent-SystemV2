type DocumentItem = {
  document_id: string
  filename: string
  created_at: string
}

type Props = {
  doc: DocumentItem
  connectedDocs: DocumentItem[]
  onGoToAnalysis: () => void
}

const formatDate = (dateStr: string) =>
  new Date(dateStr).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' })

export default function SelectedDocument({ doc, connectedDocs, onGoToAnalysis }: Props) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4 flex flex-col gap-3">
      <div>
        <p className="text-sm font-semibold text-gray-700 dark:text-gray-200 truncate">{doc.filename}</p>
        <p className="text-xs text-gray-400 mt-0.5">{formatDate(doc.created_at)}</p>
      </div>
      <div>
        <p className="text-xs text-gray-400 mb-1.5">연관 문서 {connectedDocs.length}개</p>
        <div className="flex flex-col gap-1">
          {connectedDocs.length === 0 ? (
            <p className="text-xs text-gray-300 dark:text-gray-600">연관된 문서가 없어요</p>
          ) : (
            connectedDocs.map((d) => (
              <div key={d.document_id} className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-700 px-2.5 py-1.5 rounded-lg">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0" />
                <span className="truncate">{d.filename}</span>
              </div>
            ))
          )}
        </div>
      </div>
      <button
        onClick={onGoToAnalysis}
        className="w-full text-xs text-white bg-blue-600 px-3 py-2 rounded-lg hover:bg-blue-700"
      >
        분석 결과 보기 →
      </button>
    </div>
  )
}