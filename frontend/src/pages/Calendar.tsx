import { useState } from 'react'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'

const events = [
  { id: 1, title: '마케팅 전략 회의', time: '10:00', date: 20, color: 'bg-blue-100 dark:bg-[#1a2040] text-blue-600 dark:text-[#5b8af5] border-blue-200 dark:border-[#5b8af5]' },
  { id: 2, title: '디자인 리뷰', time: '14:00', date: 21, color: 'bg-purple-100 dark:bg-[#231a40] text-purple-600 dark:text-[#9b6af7] border-purple-200 dark:border-[#9b6af7]' },
  { id: 3, title: 'A/B 테스트 회의', time: '09:00', date: 22, color: 'bg-green-100 dark:bg-[#152a1e] text-green-600 dark:text-[#4caf82] border-green-200 dark:border-[#4caf82]' },
  { id: 4, title: '클라이언트 미팅', time: '13:00', date: 22, color: 'bg-orange-100 dark:bg-[#2a2215] text-orange-600 dark:text-[#e8a838] border-orange-200 dark:border-[#e8a838]' },
  { id: 5, title: '팀 스탠드업', time: '09:30', date: 24, color: 'bg-blue-100 dark:bg-[#1a2040] text-blue-600 dark:text-[#5b8af5] border-blue-200 dark:border-[#5b8af5]' },
  { id: 6, title: '성과 보고서 발표', time: '15:00', date: 25, color: 'bg-red-100 dark:bg-[#2a1515] text-red-600 dark:text-[#e05c5c] border-red-200 dark:border-[#e05c5c]' },
]

const weekDates = [20, 21, 22, 23, 24, 25, 26]
const weekLabels = ['월', '화', '수', '목', '금', '토', '일']
const hours = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18]

export default function Calendar() {
  const [view, setView] = useState<'week' | 'month'>('week')

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-gray-800 dark:text-white">캘린더</h1>
          <div className="flex items-center gap-1">
            <button className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
              <ChevronLeft size={14} className="text-gray-400" />
            </button>
            <span className="text-sm font-medium text-gray-700 dark:text-gray-200">2024년 5월</span>
            <button className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
              <ChevronRight size={14} className="text-gray-400" />
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
            <button onClick={() => setView('week')} className={`text-xs px-3 py-1.5 rounded-md transition ${view === 'week' ? 'bg-white dark:bg-gray-600 text-gray-700 dark:text-white font-medium' : 'text-gray-400'}`}>주간</button>
            <button onClick={() => setView('month')} className={`text-xs px-3 py-1.5 rounded-md transition ${view === 'month' ? 'bg-white dark:bg-gray-600 text-gray-700 dark:text-white font-medium' : 'text-gray-400'}`}>월간</button>
          </div>
          <button className="flex items-center gap-1.5 text-xs text-white bg-blue-600 px-3 py-2 rounded-lg hover:bg-blue-700">
            <Plus size={13} /> 일정 추가
          </button>
        </div>
      </div>

      {view === 'week' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 overflow-hidden">
          <div className="grid border-b border-gray-100 dark:border-gray-700" style={{ gridTemplateColumns: '60px repeat(7, 1fr)' }}>
            <div className="p-3 border-r border-gray-100 dark:border-gray-700" />
            {weekDates.map((date, i) => (
              <div key={i} className={`p-3 text-center border-r border-gray-100 dark:border-gray-700 last:border-0 ${date === 22 ? 'bg-blue-50 dark:bg-blue-900/30' : ''}`}>
                <p className="text-xs text-gray-400 mb-1">{weekLabels[i]}</p>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center mx-auto text-sm font-medium ${date === 22 ? 'bg-blue-600 text-white' : 'text-gray-700 dark:text-gray-200'}`}>{date}</div>
              </div>
            ))}
          </div>
          <div>
            {hours.map((hour) => (
              <div key={hour} className="grid border-b border-gray-50 dark:border-gray-700" style={{ gridTemplateColumns: '60px repeat(7, 1fr)', minHeight: '56px' }}>
                <div className="p-2 border-r border-gray-100 dark:border-gray-700 flex items-start justify-end">
                  <span className="text-xs text-gray-400 dark:text-gray-400">{hour}:00</span>
                </div>
                {weekDates.map((date, i) => {
                  const dayEvents = events.filter(e => e.date === date && parseInt(e.time) === hour)
                  return (
                    <div key={i} className={`p-1 border-r border-gray-50 dark:border-gray-700 last:border-0 ${date === 22 ? 'bg-blue-50/30 dark:bg-blue-900/10' : ''}`}>
                      {dayEvents.map(event => (
                        <div key={event.id} className={`text-xs p-1.5 rounded-lg border mb-1 cursor-pointer ${event.color}`}>
                          <p className="font-medium truncate">{event.title}</p>
                          <p className="opacity-70">{event.time}</p>
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      {view === 'month' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 overflow-hidden">
          <div className="grid grid-cols-7 border-b border-gray-100 dark:border-gray-700">
            {['일', '월', '화', '수', '목', '금', '토'].map((day, i) => (
              <div key={i} className="p-3 text-center text-xs font-medium text-gray-400 border-r border-gray-100 dark:border-gray-700 last:border-0">{day}</div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {Array.from({ length: 35 }, (_, i) => {
              const d = i - 2
              const date = d <= 0 || d > 31 ? null : d
              return (
                <div key={i} className={`min-h-20 p-2 border-r border-b border-gray-100 dark:border-gray-700 ${!date ? 'bg-gray-50/50 dark:bg-gray-900/30' : ''}`}>
                  {date && (
                    <>
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs mb-1 ${date === 22 ? 'bg-blue-600 text-white font-medium' : 'text-gray-500 dark:text-gray-400'}`}>{date}</div>
                      {events.filter(e => e.date === date).map(event => (
                        <div key={event.id} className={`text-xs px-1.5 py-0.5 rounded mb-0.5 truncate cursor-pointer border ${event.color}`}>{event.title}</div>
                      ))}
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}