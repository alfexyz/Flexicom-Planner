export function TrendArrow({ trend }: { trend: string }) {
  if (trend === 'rising')  return <span className="text-emerald-400 font-bold">↑</span>
  if (trend === 'falling') return <span className="text-red-400 font-bold">↓</span>
  return <span className="text-gray-500">→</span>
}
