import { useState } from 'react'
import { X } from 'lucide-react'

const keywords = [
  { word: '마케팅', size: 28, color: '#6366f1', x: 50, y: 45 },
  { word: '전략', size: 22, color: '#818cf8', x: 72, y: 25 },
  { word: '캠페인', size: 22, color: '#3b82f6', x: 25, y: 30 },
  { word: '예산', size: 18, color: '#8b5cf6', x: 70, y: 65 },
  { word: '유튜브', size: 16, color: '#6b7280', x: 20, y: 60 },
  { word: '인스타그램', size: 15, color: '#6b7280', x: 45, y: 75 },
  { word: '성과', size: 17, color: '#14b8a6', x: 15, y: 45 },
  { word: '목표', size: 13, color: '#9ca3af', x: 60, y: 82 },
  { word: '브랜드', size: 13, color: '#9ca3af', x: 78, y: 48 },
  { word: '광고', size: 13, color: '#9ca3af', x: 33, y: 18 },
  { word: '실행', size: 12, color: '#9ca3af', x: 12, y: 75 },
  { word: '콘텐츠', size: 15, color: '#9ca3af', x: 55, y: 15 },
]

// 빈도 그래프에는 상위 6개만 보여주고, "전체 보기"에서 전체 목록을 보여줄 거라
// 미리보기용(top6)과 전체용(full) 데이터를 분리해둠
// → 나중에 API 연결 시 이 fullKeywordList 하나만 실제 응답으로 교체하면 됨
const fullKeywordList = [
  { word: '마케팅', count: 24 },
  { word: '캠페인', count: 18 },
  { word: '전략', count: 15 },
  { word: '예산', count: 12 },
  { word: '유튜브', count: 9 },
  { word: '인스타그램', count: 8 },
  { word: '성과', count: 7 },
  { word: '브랜드', count: 6 },
  { word: '광고', count: 5 },
  { word: '콘텐츠', count: 5 },
  { word: '목표', count: 4 },
  { word: '실행', count: 3 },
]

const maxCount = fullKeywordList[0].count // 막대 너비 비율 계산 기준값

export default function TabKeyword() {
  const [showAll, setShowAll] = useState(false) // 전체 키워드 모달 열림 여부

  const previewList = fullKeywordList.slice(0, 6) // 빈도 그래프 미리보기용 상위 6개

  return (
    <div className="grid grid-cols-2 gap-4">
      {/* 워드 클라우드 */}
      <div className="bg-white dark:bg-[#1c1a1a] rounded-xl border border-gray-100 dark:border-gray-700 p-6">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">핵심 키워드</h3>
        <div className="w-full" style={{ aspectRatio: '4/3', maxHeight: '300px' }}>
          <svg
            viewBox="0 0 300 220"
            className="w-full h-full"
            xmlns="http://www.w3.org/2000/svg"
          >
            {keywords.map((kw, i) => (
              <text
                key={i}
                x={`${kw.x}%`}
                y={`${kw.y}%`}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={kw.size}
                fontWeight={kw.size >= 20 ? 600 : 400}
                fill={kw.color}
                style={{ cursor: 'pointer' }}
              >
                {kw.word}
              </text>
            ))}
          </svg>
        </div>
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-xs text-blue-500 hover:text-blue-600 transition-colors"
        >
          전체 키워드 보기 →
        </button>
      </div>

      {/* 키워드 빈도 (미리보기 상위 6개) */}
      <div className="bg-white dark:bg-[#1c1a1a] rounded-xl border border-gray-100 dark:border-gray-700 p-6">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-4">키워드 빈도</h3>
        <div className="flex flex-col gap-3">
          {previewList.map((kw, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="text-xs text-gray-600 dark:text-gray-300 w-20">{kw.word}</span>
              <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5">
                <div
                  className="bg-blue-400 h-1.5 rounded-full"
                  style={{ width: `${(kw.count / maxCount) * 100}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 w-6 text-right">{kw.count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 전체 키워드 모달 */}
      {showAll && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={() => setShowAll(false)} // 배경 클릭 시 닫힘
        >
          <div
            className="bg-white dark:bg-[#1c1a1a] rounded-xl border border-gray-100 dark:border-gray-700 w-[420px] max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()} // 모달 내부 클릭은 닫힘 방지
          >
            <div className="flex items-center justify-between p-5 border-b border-gray-100 dark:border-gray-700">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                전체 키워드 ({fullKeywordList.length}개)
              </h3>
              <button
                onClick={() => setShowAll(false)}
                className="w-6 h-6 flex items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                <X size={14} className="text-gray-400" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3">
              {fullKeywordList.map((kw, i) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-xs text-gray-400 w-5">{i + 1}</span>
                  <span className="text-xs text-gray-600 dark:text-gray-300 w-20 flex-shrink-0">{kw.word}</span>
                  <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5">
                    <div
                      className="bg-blue-400 h-1.5 rounded-full"
                      style={{ width: `${(kw.count / maxCount) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 w-6 text-right">{kw.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}