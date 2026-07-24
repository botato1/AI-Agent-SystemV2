import { useState } from 'react'
import { Plus, Send, Trash2 } from 'lucide-react'

const emailList = [
  { id: 1, to: 'kim@example.com', subject: '마케팅 전략 회의 결과 공유', preview: '안녕하세요, 오늘 회의에서 논의된 내용을 공유드립니다.', time: '오후 2:30', status: '초안' },
  { id: 2, to: 'lee@example.com', subject: '광고 소재 제작 요청', preview: 'A/B 테스트를 위한 광고 소재 3종 제작을 요청드립니다.', time: '오후 1:45', status: '초안' },
  { id: 3, to: 'park@example.com', subject: '랜딩페이지 디자인 수정 건', preview: '랜딩페이지 디자인 수정 관련하여 말씀드릴 내용이 있습니다.', time: '오전 11:20', status: '발송완료' },
]

const defaultBody = `안녕하세요, 김나연입니다.

오늘 마케팅 전략 회의에서 논의된 주요 내용을 공유드립니다.

📌 주요 결정사항
- 신규 광고 소재 3종 제작 (담당: 김나연, 기한: 5월 25일)
- A/B 테스트 계획 수립 (담당: 이지원, 기한: 5월 26일)
- 랜딩페이지 디자인 수정 (담당: 박민수, 기한: 5월 21일)

📅 다음 회의: 5월 27일 (월) 오전 10시

궁금한 점이 있으시면 언제든지 연락주세요.

감사합니다.
김나연 드림`

export default function Email() {
  const [selectedId, setSelectedId] = useState(1)
  const [body, setBody] = useState(defaultBody)
  const [subject, setSubject] = useState('마케팅 전략 회의 결과 공유')
  const [to, setTo] = useState('kim@example.com')

  return (
    <div className="flex gap-4 h-[calc(100vh-80px)]">

      {/* 왼쪽 목록 */}
      <div className="w-64 flex flex-col gap-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold text-gray-800 dark:text-white">이메일 초안</h1>
          <button className="flex items-center gap-1 text-xs text-white bg-blue-600 px-2.5 py-1.5 rounded-lg hover:bg-blue-700">
            <Plus size={12} /> 새 이메일
          </button>
        </div>

        <div className="flex flex-col gap-2">
          {emailList.map((email) => (
            <div
              key={email.id}
              onClick={() => {
                setSelectedId(email.id)
                setSubject(email.subject)
                setTo(email.to)
              }}
              className={`p-3 rounded-xl border cursor-pointer transition ${
                selectedId === email.id
                  ? 'border-blue-200 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/30'
                  : 'border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-blue-100'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-500 dark:text-gray-400 truncate">{email.to}</span>
                <span className="text-xs text-gray-300 dark:text-gray-600">{email.time}</span>
              </div>
              <p className="text-xs font-medium text-gray-700 dark:text-gray-200 truncate mb-1">{email.subject}</p>
              <div className="flex items-center justify-between">
                <p className="text-xs text-gray-400 truncate flex-1">{email.preview}</p>
                <span className={`text-xs px-1.5 py-0.5 rounded-full ml-1 flex-shrink-0 ${
                  email.status === '초안'
                    ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-500'
                    : 'bg-green-100 dark:bg-green-900/30 text-green-500'
                }`}>
                  {email.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 오른쪽 편집기 */}
      <div className="flex-1 bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 flex flex-col">
        <div className="p-4 border-b border-gray-100 dark:border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-gray-400 w-10">받는이</span>
            <input
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="flex-1 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-none border-b border-gray-100 dark:border-gray-600 pb-1 focus:border-blue-300"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 w-10">제목</span>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="flex-1 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent outline-none border-b border-gray-100 dark:border-gray-600 pb-1 focus:border-blue-300"
            />
          </div>
        </div>

        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="flex-1 p-4 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-none resize-none leading-relaxed"
          placeholder="이메일 내용을 입력하세요..."
        />

        <div className="p-4 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
          <button className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-400 transition">
            <Trash2 size={13} /> 삭제
          </button>
          <div className="flex gap-2">
            <button className="text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-600 px-3 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
              임시저장
            </button>
            <button className="flex items-center gap-1.5 text-xs text-white bg-blue-600 px-3 py-1.5 rounded-lg hover:bg-blue-700">
              <Send size={13} /> 발송하기
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}