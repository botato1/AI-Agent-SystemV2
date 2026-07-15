type Node = {
  id: string
  label: string
  group: number
  size: number
}

type Props = {
  nodes: Node[]
  selected: string | null
  onSelect: (id: string) => void
  getGroupColor: (group: number) => string
}

export default function DocumentList({ nodes, selected, onSelect, getGroupColor }: Props) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-100 dark:border-gray-700 flex flex-col" style={{ height: '400px' }}>
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex-shrink-0">
        <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          전체 문서 ({nodes.length})
        </h3>
      </div>
      <div className="overflow-y-auto flex-1 p-2 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-600 [&::-webkit-scrollbar-track]:bg-transparent">
        <div className="flex flex-col gap-0.5">
          {nodes.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-4">문서가 없어요</p>
          ) : (
            nodes.map((node) => (
              <div
                key={node.id}
                onClick={() => {
                  console.log(JSON.stringify(node)) // ← 이 줄 추가
                  onSelect(node.id)
                }}
                className={`flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-lg cursor-pointer transition ${
                  selected === node.id
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: getGroupColor(node.group) }} />
                <span className="truncate">{node.label}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}