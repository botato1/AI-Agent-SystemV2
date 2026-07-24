interface Props {
  analysisData?: any
}

export default function TabOriginal({ analysisData }: Props) {
  const filename = analysisData?.filename ?? '문서'
  const content = analysisData?.raw?.original_text || '내용을 불러올 수 없습니다.'
  const createdAt = analysisData?.created_at
    ? new Date(analysisData.created_at).toLocaleDateString('ko-KR')
    : '—'

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-100 dark:border-gray-700">
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">{filename}</h3>
          <p className="text-xs text-gray-400 mt-0.5">{createdAt}</p>
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-400">PDF</span>
      </div>
      <pre className="text-sm text-gray-700 dark:text-gray-300 leading-7 whitespace-pre-wrap font-sans">
        {content}
      </pre>
    </div>
  )
}