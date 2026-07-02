interface SttSegment {
  speaker: string
  start: number
  end: number
  text: string
}

interface Props {
  segments: SttSegment[]
}

const formatTime = (seconds: number) => {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0')
  const s = Math.floor(seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

const speakerColors = [
  'text-blue-500 dark:text-blue-400',
  'text-purple-500 dark:text-purple-400',
  'text-green-500 dark:text-green-400',
  'text-orange-500 dark:text-orange-400',
]

export default function TabScript({ segments }: Props) {
  const speakerList = [...new Set(segments.map(s => s.speaker))]

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-6">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-4">전체 텍스트</h3>
      {segments.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">스크립트 데이터가 없어요</p>
      ) : (
        <div className="flex flex-col gap-4">
          {segments.map((item, i) => {
            const colorIdx = speakerList.indexOf(item.speaker) % speakerColors.length
            return (
              <div key={i} className="flex gap-3">
                <div className="flex-shrink-0 text-right w-12">
                  <span className="text-xs text-gray-400">{formatTime(item.start)}</span>
                </div>
                <div className="flex-1">
                  <span className={`text-xs font-semibold mr-2 ${speakerColors[colorIdx]}`}>
                    {item.speaker}
                  </span>
                  <span className="text-xs text-gray-600 dark:text-gray-300">{item.text}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}