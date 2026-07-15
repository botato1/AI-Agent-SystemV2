interface SttSegment {
  speaker: string
  start: number
  end: number
  text: string
}

interface Props {
  segments: SttSegment[]
}

const speakerColors = [
  { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-600 dark:text-blue-400', bar: 'bg-blue-500' },
  { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-600 dark:text-purple-400', bar: 'bg-purple-500' },
  { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-600 dark:text-green-400', bar: 'bg-green-500' },
  { bg: 'bg-orange-100 dark:bg-orange-900/30', text: 'text-orange-600 dark:text-orange-400', bar: 'bg-orange-500' },
]

export default function TabSpeakers({ segments }: Props) {
  const speakerList = [...new Set(segments.map(s => s.speaker))]

  const speakerStats = speakerList.map(speaker => {
    const speakerSegments = segments.filter(s => s.speaker === speaker)
    const totalTime = speakerSegments.reduce((acc, s) => acc + (s.end - s.start), 0)
    return { speaker, count: speakerSegments.length, totalTime }
  })

  const totalTime = speakerStats.reduce((acc, s) => acc + s.totalTime, 0)

  if (segments.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
        <p className="text-xs text-gray-400 text-center py-4">발화자 데이터가 없어요</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {speakerStats.map((s, i) => {
        const color = speakerColors[i % speakerColors.length]
        const percent = totalTime > 0 ? Math.round((s.totalTime / totalTime) * 100) : 0
        return (
          <div key={s.speaker} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className={`w-10 h-10 ${color.bg} rounded-full flex items-center justify-center`}>
                <span className={`text-sm font-medium ${color.text}`}>{i + 1}</span>
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">{s.speaker}</p>
                <p className="text-xs text-gray-400">발언 비율 {percent}%</p>
              </div>
            </div>
            <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-2 mb-2">
              <div className={`${color.bar} h-2 rounded-full`} style={{ width: `${percent}%` }} />
            </div>
            <p className="text-xs text-gray-400">{s.count}개 발화</p>
          </div>
        )
      })}
    </div>
  )
}