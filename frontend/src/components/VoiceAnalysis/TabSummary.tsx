interface Props {
  duration: string
  segmentCount: number
}

const timeline = [
  { time: '00:00', text: '회의 시작 및 참석자 소개' },
  { time: '02:15', text: '지난 캠페인 성과 리뷰' },
  { time: '14:30', text: '신규 채널 전략 논의' },
  { time: '27:45', text: '다음 분기 키 메시지 및 예산 논의' },
  { time: '42:10', text: '마무리 및 다음 회의 일정' },
]

const actionItems = [
  { title: '신규 채널 콘텐츠 캘린더 작성', assignee: '박민수', due: '05.20' },
  { title: '다음 분기 예산안 최종 검토', assignee: '이애전', due: '05.21' },
  { title: '캠페인 키 메시지 정리', assignee: '김나연', due: '05.22' },
  { title: '성과 리포트 템플릿 업데이트', assignee: '최지우', due: '05.23' },
]

export default function TabSummary({ duration, segmentCount }: Props) {
  const analysisStats = [
    { label: '총 발언 시간', value: duration },
    { label: '발화 구간', value: `${segmentCount}개` },
    { label: '추출된 Task', value: '—' },
    { label: '분석 소요 시간', value: '—' },
  ]

  return (
    <div className="flex flex-col gap-4">
      {/* 통계 카드 */}
      <div className="grid grid-cols-4 gap-3">
        {analysisStats.map((stat, i) => (
          <div key={i} className="bg-white dark:bg-[#1c1a1a] rounded-xl border border-gray-100 dark:border-gray-700 p-4 text-center">
            <p className="text-lg font-semibold text-blue-600 dark:text-blue-400">{stat.value}</p>
            <p className="text-xs text-gray-400 mt-1">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* AI 요약 */}
        <div className="bg-white dark:bg-[#1c1a1a] rounded-xl border border-gray-100 dark:border-gray-700 p-4">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">AI 요약</h3>
          <p className="text-xs text-gray-400 text-center py-4">백엔드 연동 후 표시됩니다</p>
        </div>

        {/* 타임라인 */}
        <div className="bg-white dark:bg-[#1c1a1a] rounded-xl border border-gray-100 dark:border-gray-700 p-4">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">주요 내용</h3>
          <div className="flex flex-col gap-2">
            {timeline.map((item, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-xs text-blue-500 font-medium w-10 flex-shrink-0">{item.time}</span>
                <span className="text-xs text-gray-600 dark:text-gray-300">{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 액션 아이템 */}
        <div className="bg-white dark:bg-[#1c1a1a] rounded-xl border border-gray-100 dark:border-gray-700 p-4">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">액션 아이템</h3>
          <div className="flex flex-col gap-2">
            {actionItems.map((item, i) => (
              <div key={i} className="flex items-center gap-2">
                <input type="checkbox" className="w-3.5 h-3.5 accent-blue-500 flex-shrink-0" />
                <span className="text-xs text-gray-600 dark:text-gray-300 flex-1 truncate">{item.title}</span>
                <span className="text-xs text-gray-400 flex-shrink-0">{item.assignee} {item.due}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}