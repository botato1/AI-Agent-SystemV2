//카드뷰 탭 - Task를 카드 형태로 표시
const tasks = [
  { title: '신규 광고 소재 3종 제작', assignee: '김나연', due: '5월 25일(토)', status: '진행중', statusColor: 'bg-orange-100 text-orange-600' },
  { title: 'A/B 테스트 계획 수립', assignee: '이지원', due: '5월 26일(일)', status: '진행중', statusColor: 'bg-orange-100 text-orange-600' },
  { title: '랜딩페이지 디자인 수정', assignee: '박민수', due: '5월 21일(화)', status: '완료', statusColor: 'bg-blue-100 text-blue-600' },
  { title: '성과 측정 지표 정의', assignee: '박민수', due: '5월 23일(목)', status: '대기', statusColor: 'bg-gray-100 text-gray-500' },
]

export default function TabCards() {
  return (
    <div className="grid grid-cols-2 gap-4">
      {tasks.map((task, i) => (
        <div key={i} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4 hover:border-blue-200 transition">
          <div className="flex items-center justify-between mb-2">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${task.statusColor}`}>{task.status}</span>
            <span className="text-xs text-gray-400">{task.due}</span>
          </div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">{task.title}</p>
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-blue-100 dark:bg-blue-900 rounded-full flex items-center justify-center">
              <span className="text-xs text-blue-600 dark:text-blue-300">{task.assignee[0]}</span>
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">{task.assignee}</span>
          </div>
        </div>
      ))}
    </div>
  )
}