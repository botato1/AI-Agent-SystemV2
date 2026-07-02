const relatedDocs = [
  { name: '2023년 하반기 마케팅 전략.pdf', similarity: 92, date: '2023.11.15', type: 'PDF' },
  { name: '광고 소재 제작 가이드.docx', similarity: 87, date: '2024.03.20', type: 'DOCX' },
  { name: 'A/B 테스트 결과 보고서.pdf', similarity: 78, date: '2024.04.10', type: 'PDF' },
]

const typeColor: Record<string, string> = {
  PDF: 'text-[#818cf8]',
  DOCX: 'text-[#34d399]',
}

export default function TabRelated() {
  return (
    <div className="flex flex-col gap-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-5">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-4">연관 문서</h3>
        <div className="flex flex-col gap-3">
          {relatedDocs.map((doc, i) => (
            <div key={i} className="flex items-center gap-4 p-3 rounded-lg bg-gray-50 dark:bg-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition cursor-pointer">
              <span className={`text-xs font-medium flex-shrink-0 ${typeColor[doc.type]}`} style={{ color: doc.type === 'PDF' ? '#818cf8' : '#34d399' }}>
                {doc.type}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-700 dark:text-gray-200 truncate">{doc.name}</p>
                <p className="text-xs text-gray-400 mt-0.5">{doc.date}</p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <div className="w-16 h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-blue-400"
                    style={{ width: `${doc.similarity}%` }}
                  />
                </div>
                <span className="text-xs text-blue-500 font-medium">{doc.similarity}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}