import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { api } from '../api/client'
import { Card, CardTitle } from '../components/ui/Card'
import { PageError, Spinner } from '../components/ui/Spinner'

const RON = (n: number) =>
  new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'RON', maximumFractionDigits: 0 }).format(n)

const DONUT_COLORS: Record<string, string> = {
  Sănătos: '#10b981',
  Lent:    '#f59e0b',
  Critic:  '#ef4444',
  Mort:    '#6b7280',
}

export default function Overview() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useQuery({ queryKey: ['overview'], queryFn: api.overview })

  if (isLoading) return <Spinner />
  if (error || !data) return <PageError message="Eroare la încărcarea datelor" />

  const donutData = [
    { name: 'Sănătos', value: data.inventory.healthy_pct },
    { name: 'Lent',    value: data.inventory.slow_pct },
    { name: 'Critic',  value: data.inventory.critical_pct },
    { name: 'Mort',    value: data.inventory.dead_pct },
  ].filter(d => d.value > 0)

  const ac = data.alert_counts

  return (
    <div className="space-y-6">
      {/* Vânzări strip */}
      <div>
        <div className="flex items-baseline gap-2 mb-2">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Vânzări nete</p>
          <p className="text-xs text-gray-600">— total facturat pe facturi emise, fără storno</p>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Luna Curentă',             sub: 'vânzări din luna în curs',          value: data.revenue.this_month,           highlight: true },
            { label: 'Luna Trecută',             sub: 'vânzări din luna anterioară',        value: data.revenue.last_month },
            { label: 'Aceeași Lună / An Trecut', sub: 'aceeași lună, cu un an în urmă',     value: data.revenue.same_month_last_year },
          ].map(({ label, sub, value, highlight }) => (
            <Card key={label}>
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">{label}</p>
              <p className="text-xs text-gray-600 mb-2">{sub}</p>
              <p className={`text-3xl font-bold tabular-nums ${highlight ? 'text-white' : 'text-gray-300'}`}>
                {RON(value)}
              </p>
              {highlight && data.revenue.trend_pct !== null && (
                <p className={`text-sm mt-1 ${data.revenue.trend_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {data.revenue.trend_pct >= 0 ? '+' : ''}{data.revenue.trend_pct}% față de luna trecută
                </p>
              )}
            </Card>
          ))}
        </div>
      </div>

      {/* Sănătatea stocului + capital imobilizat */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardTitle>Sănătatea Stocului</CardTitle>
          <div className="flex items-center gap-6">
            <ResponsiveContainer width={160} height={160}>
              <PieChart>
                <Pie data={donutData} cx="50%" cy="50%" innerRadius={50} outerRadius={70}
                     dataKey="value" strokeWidth={0}>
                  {donutData.map((d) => <Cell key={d.name} fill={DONUT_COLORS[d.name]} />)}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  formatter={(v) => [`${Number(v).toFixed(1)}%`]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-2 text-sm">
              {[
                { label: 'Sănătos', pct: data.inventory.healthy_pct,  color: 'bg-emerald-500' },
                { label: 'Lent',    pct: data.inventory.slow_pct,     color: 'bg-yellow-500' },
                { label: 'Critic',  pct: data.inventory.critical_pct, color: 'bg-red-500' },
                { label: 'Mort',    pct: data.inventory.dead_pct,     color: 'bg-gray-500' },
              ].map(({ label, pct, color }) => (
                <div key={label} className="flex items-center gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full ${color}`} />
                  <span className="text-gray-400 w-16">{label}</span>
                  <span className="text-white font-medium tabular-nums">{pct.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card>
          <CardTitle>Capital Imobilizat în Stoc</CardTitle>
          <p className="text-4xl font-bold text-white tabular-nums mb-4">{RON(data.inventory.total_ron)}</p>
          <div className="space-y-2 text-sm">
            {[
              { label: 'Stoc sănătos', value: data.inventory.healthy_ron,  cls: 'text-emerald-400' },
              { label: 'Stoc lent',    value: data.inventory.slow_ron,     cls: 'text-yellow-400' },
              { label: 'Stoc critic',  value: data.inventory.critical_ron, cls: 'text-red-400' },
              { label: 'Stoc mort',    value: data.inventory.dead_ron,     cls: 'text-gray-400' },
            ].map(({ label, value, cls }) => (
              <div key={label} className="flex justify-between">
                <span className="text-gray-500">{label}</span>
                <span className={`font-medium tabular-nums ${cls}`}>{RON(value)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Sumar alerte + alerte prioritare */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardTitle>Sumar Alerte</CardTitle>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Critic',           count: ac.critical,           color: 'text-red-400',    bg: 'bg-red-900/30' },
              { label: 'Comandă Acum',     count: ac.order_now,          color: 'text-orange-400', bg: 'bg-orange-900/30' },
              { label: 'Atenție',          count: ac.watch,              color: 'text-yellow-400', bg: 'bg-yellow-900/30' },
              { label: 'Stoc Mort',        count: ac.dead_stock,         color: 'text-gray-400',   bg: 'bg-gray-800' },
              { label: 'Declin',           count: ac.declining,          color: 'text-purple-400', bg: 'bg-purple-900/30' },
              { label: 'Deviere Client',   count: ac.customer_deviation, color: 'text-blue-400',   bg: 'bg-blue-900/30' },
            ].map(({ label, count, color, bg }) => (
              <button
                key={label}
                onClick={() => navigate('/alerts')}
                className={`${bg} rounded-lg p-3 text-left hover:brightness-110 transition-all`}
              >
                <p className={`text-2xl font-bold tabular-nums ${color}`}>{count}</p>
                <p className="text-xs text-gray-500 mt-0.5">{label}</p>
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <CardTitle>Alerte Prioritare</CardTitle>
          {data.top_alerts.length === 0 ? (
            <p className="text-gray-500 text-sm">Nicio alertă urgentă astăzi.</p>
          ) : (
            <div className="space-y-3">
              {data.top_alerts.map(alert => (
                <button
                  key={alert.product_code}
                  onClick={() => navigate(`/products/${alert.product_code}`)}
                  className="w-full text-left bg-gray-800 hover:bg-gray-700 rounded-lg p-3 transition-colors"
                >
                  <div className="flex justify-between items-start mb-1">
                    <span className="font-medium text-white text-sm">{alert.product_name}</span>
                    {alert.days_of_cover !== null && (
                      <span className="text-xs text-red-400 font-medium ml-2 shrink-0">
                        {Math.round(alert.days_of_cover)}z rămase
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 line-clamp-2">{alert.message}</p>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
