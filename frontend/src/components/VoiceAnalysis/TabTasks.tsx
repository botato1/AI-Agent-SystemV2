const tasks = [
  { title: '신규 채널 콘텐츠 캘린더 작성', assignee: '박민수', due: '05.20', priority: 'high', status: '진행중', statusColor: 'bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400' },
  { title: '다음 분기 예산안 최종 검토', assignee: '이애전', due: '05.21', priority: 'high', status: '진행중', statusColor: 'bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400' },
  { title: '캠페인 키 메시지 정리', assignee: '김나연', due: '05.22', priority: 'mid', status: '대기', statusColor: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400' },
  { title: '성과 리포트 템플릿 업데이트', assignee: '최지우', due: '05.23', priority: 'low', status: '대기', statusColor: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400' },
]

export default function TabTasks() {
  return (
    <div className="flex flex-col gap-3">
      {tasks.map((task, i) => (
        <div
          key={i}
          className="bg-white dark:bg-[#1c1a1a] rounded-xl border border-gray-100 dark:border-gray-700 px-5 py-4 flex items-center gap-4 hover:border-indigo-200 dark:hover:border-indigo-700 transition-colors"
        >
          {/* 번호 */}
          <span className="text-xs text-gray-300 dark:text-gray-600 w-4 flex-shrink-0">{i + 1}</span>

          {/* 할 일 제목 */}
          <p className="flex-1 text-sm text-gray-700 dark:text-gray-200">{task.title}</p>

          {/* 담당자 */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <div className="w-5 h-5 bg-indigo-100 dark:bg-indigo-900/30 rounded-full flex items-center justify-center">
              <span className="text-xs text-indigo-600 dark:text-indigo-300">{task.assignee[0]}</span>
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">{task.assignee}</span>
          </div>

          {/* 기한 */}
          <span className="text-xs text-gray-400 flex-shrink-0 w-12">{task.due}</span>

          {/* Task에 추가 버튼 */}
          <button className="flex-shrink-0 text-xs text-indigo-500 border border-indigo-200 dark:border-indigo-700 px-3 py-1.5 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors">
            Task에 추가
          </button>
        </div>
      ))}
    </div>
  )
}