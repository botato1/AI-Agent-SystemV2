interface Props {
  analysisData?: any
}

const priorityColors: Record<string, string> = {
  high: 'bg-red-400',
  medium: 'bg-amber-400',
  low: 'bg-green-400',
}
const priorityLabel: Record<string, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
}

export default function TabSummary({ analysisData }: Props) {
  const tasks = analysisData?.organized?.tasks ?? []
  const importantPoints = analysisData?.organized?.important_points ?? []
  const keywords = analysisData?.analysis?.keywords ?? []

  const analysisStats = [
    { label: '핵심 문장 추출', value: `${importantPoints.length}개` },
    { label: '감지된 액션 아이템', value: `${tasks.length}개` },
    { label: '연관 문서', value: '—' }, // 임베딩 유사도 연동 전까지는 비워둠
    { label: '페이지 수', value: analysisData?.analysis?.page_count ? `${analysisData.analysis.page_count}페이지` : '—' },
  ]

  const summaryText = analysisData?.analysis?.summary || '요약 데이터가 없습니다.'

  return (
    <div className="flex flex-col gap-4">
      {/* 분석 통계 */}
      <div className="grid grid-cols-4 gap-3">
        {analysisStats.map((stat, i) => (
          <div key={i} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4 text-center">
            <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{stat.value}</p>
            <p className="text-xs text-gray-400 mt-1">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-4">
          {/* 문서 요약 */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">문서 요약</h3>
            <p className="text-xs text-gray-600 dark:text-gray-300 leading-6">{summaryText}</p>
          </div>

          {/* 키워드 */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">키워드</h3>
            <div className="flex flex-wrap gap-2">
              {keywords.length === 0 ? (
                <p className="text-xs text-gray-400">키워드가 없어요.</p>
              ) : (
                keywords.map((tag: string, i: number) => (
                  <span key={i} className="text-xs text-gray-600 dark:text-gray-400 px-3 py-1 rounded-full border border-gray-400 dark:border-gray-500">
                    {tag}
                  </span>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          {/* Task */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">할 일 (Tasks)</h3>
              <button className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400">전체 보기 →</button>
            </div>
            {tasks.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-4">추출된 Task가 없어요</p>
            ) : (
              tasks.map((task: any) => (
                <div key={task.task_id} className="flex items-center gap-3 py-2 border-b border-gray-50 dark:border-gray-700 last:border-0">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${priorityColors[task.priority] ?? 'bg-gray-300'}`} />
                  <p className="flex-1 text-xs text-gray-700 dark:text-gray-200 truncate">{task.task}</p>
                  {task.assignee && (
                    <span className="text-xs text-gray-400 flex-shrink-0">{task.assignee}</span>
                  )}
                  <span className="text-xs text-gray-300 dark:text-gray-500 flex-shrink-0">
                    {priorityLabel[task.priority] ?? task.priority}
                  </span>
                </div>
              ))
            )}
          </div>

          {/* 저장 상태 */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">저장 상태</h3>
            <div className="flex flex-col gap-2">
              {[
                { label: '문서 처리', value: analysisData?.status === 'processed' ? '완료' : '—' },
                { label: '페이지 수', value: `${analysisData?.analysis?.page_count ?? '—'}페이지` },
                { label: 'OCR 엔진', value: analysisData?.analysis?.engines?.join(', ') ?? '—' },
              ].map((item, i) => (
                <div key={i} className="flex items-center justify-between py-1.5 border-b border-gray-50 dark:border-gray-700 last:border-0">
                  <span className="text-xs text-gray-500 dark:text-gray-400">{item.label}</span>
                  <span className="text-xs font-medium text-gray-600 dark:text-gray-400">{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}