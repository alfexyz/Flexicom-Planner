import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

import { Badge } from '../components/ui/Badge'
import { TrendArrow } from '../components/TrendArrow'
import { PageError, Spinner } from '../components/ui/Spinner'

type SortKey = 'product_name' | 'current_stock' | 'days_of_cover_adjusted' | 'margin_pct' | 'status'

const DOC_COLOR: Record<string, string> = {
  green: 'text-emerald-400',
  amber: 'text-yellow-400',
  red:   'text-red-400',
}

export default function ProductList() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useQuery({ queryKey: ['products'], queryFn: api.products })

  const [sortKey, setSortKey]   = useState<SortKey>('status')
  const [sortAsc, setSortAsc]   = useState(true)
  const [search,  setSearch]    = useState('')

  if (isLoading) return <Spinner />
  if (error || !data) return <PageError message="Eroare la încărcarea produselor" />

  const STATUS_ORDER: Record<string, number> = {
    Critical: 0, OrderNow: 1, Watch: 2, Declining: 3, OK: 4, Dead: 5,
  }

  const sorted = [...data]
    .filter(p => p.product_name.toLowerCase().includes(search.toLowerCase()) ||
                 p.product_code.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      let av: number | string, bv: number | string
      if (sortKey === 'status') {
        av = STATUS_ORDER[a.status] ?? 9
        bv = STATUS_ORDER[b.status] ?? 9
      } else if (sortKey === 'product_name') {
        av = a.product_name; bv = b.product_name
      } else {
        av = (a[sortKey] as number | null) ?? -1
        bv = (b[sortKey] as number | null) ?? -1
      }
      if (av < bv) return sortAsc ? -1 : 1
      if (av > bv) return sortAsc ? 1 : -1
      return 0
    })

  const handleSort = (key: SortKey) => {
    if (key === sortKey) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(true) }
  }

  const Th = ({ label, k }: { label: string; k: SortKey }) => (
    <th
      className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer select-none hover:text-white transition-colors"
      onClick={() => handleSort(k)}
    >
      {label} {sortKey === k ? (sortAsc ? '↑' : '↓') : ''}
    </th>
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Caută produse…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 w-72"
        />
        <span className="text-sm text-gray-500">{sorted.length} produse</span>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-800">
            <tr>
              <Th label="Produs"           k="product_name" />
              <Th label="Stoc"             k="current_stock" />
              <Th label="Zile Acoperire"   k="days_of_cover_adjusted" />
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">Cerere</th>
              <Th label="Marjă"            k="margin_pct" />
              <Th label="Status"           k="status" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {sorted.map(p => (
              <tr
                key={p.product_code}
                onClick={() => navigate(`/products/${p.product_code}`)}
                className="hover:bg-gray-800/60 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3">
                  <div className="font-medium text-white">{p.product_name}</div>
                  <div className="text-xs text-gray-500">{p.product_code}</div>
                </td>
                <td className="px-4 py-3 tabular-nums text-gray-300">{p.current_stock.toFixed(0)}</td>
                <td className="px-4 py-3 tabular-nums">
                  {p.days_of_cover_adjusted !== null ? (
                    <span className={`font-medium ${DOC_COLOR[p.color]}`}>
                      {Math.round(p.days_of_cover_adjusted)}z
                    </span>
                  ) : (
                    <span className="text-gray-600">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2 text-gray-300">
                    <TrendArrow trend={p.trend} />
                    <span className="tabular-nums text-xs">{p.weekly_demand.toFixed(1)}/săpt</span>
                  </div>
                </td>
                <td className="px-4 py-3 tabular-nums text-gray-300">
                  {p.margin_pct !== null ? `${p.margin_pct.toFixed(1)}%` : '—'}
                </td>
                <td className="px-4 py-3">
                  <Badge label={p.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
