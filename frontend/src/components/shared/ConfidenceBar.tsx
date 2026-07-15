type Props = {
  confidence: number
  onReview: () => void
}

export default function ConfidenceBar({ confidence, onReview }: Props) {
  const getColor = () => {
    if (confidence >= 90) return { bar: 'bg-green-400', text: 'text-green-500', msg: '신뢰도가 높아요.' }
    if (confidence >= 70) return { bar: 'bg-amber-400', text: 'text-amber-500', msg: '신뢰도가 보통이에요. 재검토를 권장합니다.' }
    return { bar: 'bg-red-400', text: 'text-red-500', msg: '신뢰도가 낮아요. 재검토가 필요합니다.' }
  }

  const { bar, text, msg } = getColor()

  return (
    <div className="flex items-center gap-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 p-4 mb-6">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">분석 신뢰도</span>
          <span className={`text-xs font-bold ${text}`}>{confidence}%</span>
        </div>
        <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1.5">
          <div className={`${bar} h-1.5 rounded-full transition-all duration-500`} style={{ width: `${confidence}%` }} />
        </div>
        <p className="text-xs text-gray-400 mt-1.5">{msg}</p>
      </div>
      <button
  onClick={onReview}
  className="flex-shrink-0 text-xs text-white px-4 py-2 rounded-lg transition bg-blue-500 hover:bg-blue-600"
>
  재검토 요청
</button>
    </div>
  )
}