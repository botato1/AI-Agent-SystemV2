import { useState } from 'react'
import { useToast } from '../App'

const BASE_URL = import.meta.env.VITE_API_URL

export default function Settings() {
  const { showToast } = useToast()
  const [notifications, setNotifications] = useState({
    analysisComplete: true,
    taskDeadline: true,
  })

  const toggleNotification = async (key: keyof typeof notifications) => {
    if (!notifications[key] && 'Notification' in window) {
      await Notification.requestPermission()
    }
    setNotifications(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const handleDeleteAllChats = async () => {
    if (!confirm('채팅 기록을 전체 삭제할까요? 복구할 수 없어요.')) return
    try {
      await fetch(`${BASE_URL}/api/conversations`, { method: 'DELETE' })
      showToast('채팅 기록이 삭제되었습니다.', 'success')
    } catch {
      showToast('삭제 중 오류가 발생했어요.', 'error')
    }
  }

  return (
    <div className="max-w-xl">
      <div className="mb-6">
        <h1 className="text-lg font-bold text-gray-800 dark:text-white">설정</h1>
        <p className="text-xs text-gray-400 mt-1">앱 설정을 관리하세요</p>
      </div>

      <div className="flex flex-col gap-4">

        {/* 알림 */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-5">
          <h2 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">알림</h2>
          <div className="flex flex-col">
            {[
              { key: 'analysisComplete', label: '문서 분석 완료 알림', desc: '분석이 완료되면 알림을 받아요' },
              { key: 'taskDeadline', label: '업무 마감 알림', desc: '업무 마감 1일 전에 알림을 받아요' },
            ].map((item) => (
              <div key={item.key} className="flex items-center justify-between py-3 border-b border-gray-50 dark:border-gray-700 last:border-0">
                <div>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{item.label}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{item.desc}</p>
                </div>
                <button
                  onClick={() => toggleNotification(item.key as keyof typeof notifications)}
                  className={`w-10 h-5 rounded-full relative transition-colors ${
                    notifications[item.key as keyof typeof notifications] ? 'bg-blue-500' : 'bg-gray-200 dark:bg-gray-600'
                  }`}
                >
                  <div className={`w-4 h-4 bg-white rounded-full absolute top-0.5 shadow-sm transition-all ${
                    notifications[item.key as keyof typeof notifications] ? 'right-0.5' : 'left-0.5'
                  }`} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* 데이터 */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-5">
          <h2 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">데이터</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200">채팅 기록 전체 삭제</p>
              <p className="text-xs text-gray-400 mt-0.5">모든 대화 기록을 삭제해요. 복구할 수 없어요.</p>
            </div>
            <button
              onClick={handleDeleteAllChats}
              className="text-xs text-red-500 border border-red-200 dark:border-red-800 px-3 py-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition flex-shrink-0"
            >
              삭제하기
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}