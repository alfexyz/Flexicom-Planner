import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Area, CartesianGrid, ComposedChart, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api/client'
import { Card, CardTitle } from '../components/ui/Card'
import { PageError, Spinner } from '../components/ui/Spinner'
import { TrendArrow } from '../components/TrendArrow'

const METHOD_LABEL: Record<string, string> = {
  xgboost:        'XGBoost',
  croston:        'Croston TSB',
  trend_seasonal: 'Trend + Sezonalitate',
  no_data:        'Date insuficiente',
}

const RON = (n: number) =>
  new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 }).format(n) + ' RON'

const MONTH_NAMES = ['', 'Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
                        'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const TREND_LABEL: Record<string, string> = {
  rising:  'crescătoare',
  flat:    'stabilă',
  falling: 'scăzătoare',
}

const MARGIN_TREND_LABEL: Record<string, string> = {
  improving:   'în creștere',
  stable:      'stabilă',
  compressing: 'în compresie',
}

export default function ProductDetail() {
  const { code } = useParams<{ code: string }>()
  const navigate  = useNavigate()
  const { data: p, isLoading, error } = useQuery({
    queryKey: ['product', code],
    queryFn:  () => api.product(code!),
    enabled:  !!code,
  })
  const { data: fc } = useQuery({
    queryKey: ['forecast', code],
    queryFn:  () => api.forecast(code!),
    enabled:  !!code,
  })

  if (isLoading) return <Spinner />
  if (error || !p) return <PageError message="Produs negăsit" />

  const docColor = p.color === 'green' ? 'text-emerald-400' : p.color === 'amber' ? 'text-yellow-400' : 'text-red-400'

  // Seasonality bar data
  const seasonData = Object.entries(p.seasonality_indices).map(([m, idx]) => ({
    month: MONTH_NAMES[Number(m)],
    index: Number(idx.toFixed(2)),
  }))

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button onClick={() => navigate('/products')} className="text-xs text-gray-500 hover:text-gray-300 mb-1">
            ← Produse
          </button>
          <h1 className="text-xl font-bold text-white">{p.product_name}</h1>
          <p className="text-sm text-gray-500">{p.product_code}</p>
        </div>
        {p.below_rop && (
          <div className="bg-orange-900/40 border border-orange-700 rounded-lg px-4 py-2 text-sm text-orange-300">
            Sub punctul de reaprovizionare — comandă {p.suggested_order_qty} unități ({p.estimated_cost_ron ? RON(p.estimated_cost_ron) : ''})
          </div>
        )}
      </div>

      {/* Cifre cheie */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Stoc Curent',      value: p.current_stock.toFixed(0),          unit: 'unități' },
          { label: 'Zile Acoperire',   value: p.days_of_cover_adjusted?.toFixed(0) ?? '—', unit: 'zile', cls: docColor },
          { label: 'Cerere Săptămânală', value: p.weekly_demand.toFixed(1),         unit: 'unități/săpt' },
          { label: 'Marjă Brută',      value: p.current_margin_pct != null ? `${p.current_margin_pct.toFixed(1)}%` : '—', unit: '' },
        ].map(({ label, value, unit, cls }) => (
          <Card key={label}>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
            <p className={`text-3xl font-bold tabular-nums ${cls ?? 'text-white'}`}>{value}</p>
            {unit && <p className="text-xs text-gray-600 mt-0.5">{unit}</p>}
          </Card>
        ))}
      </div>

      {/* Evoluția marjei */}
      {p.monthly_margin_history.length > 0 && (
        <Card>
          <CardTitle>
            Evoluția Marjei
            {p.cost_increase_alert && (
              <span className="ml-3 text-xs text-orange-400 normal-case font-normal">
                ⚠ Cost +{p.cost_increase_pct?.toFixed(1)}% în ultimele 6 luni
              </span>
            )}
          </CardTitle>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={p.monthly_margin_history} margin={{ left: 0, right: 12, top: 5, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="month" tick={{ fill: '#6b7280', fontSize: 11 }} tickLine={false} axisLine={false}
                tickFormatter={v => v.slice(2)} />
              <YAxis yAxisId="price" orientation="right" tick={{ fill: '#6b7280', fontSize: 11 }}
                tickLine={false} axisLine={false} tickFormatter={v => `${v} RON`} />
              <YAxis yAxisId="pct" tick={{ fill: '#6b7280', fontSize: 11 }}
                tickLine={false} axisLine={false} tickFormatter={v => `${v}%`} domain={[0, 80]} />
              <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                labelStyle={{ color: '#9ca3af' }} />
              <Legend wrapperStyle={{ color: '#6b7280', fontSize: 12 }} />
              <Line yAxisId="price" dataKey="avg_sell_price" name="Preț vânzare" stroke="#60a5fa" dot={false} strokeWidth={2} />
              <Line yAxisId="price" dataKey="avg_buy_price"  name="Preț achiziție" stroke="#f87171" dot={false} strokeWidth={2} />
              <Line yAxisId="pct"   dataKey="margin_pct"     name="Marjă %"       stroke="#34d399" dot={false} strokeWidth={2} strokeDasharray="4 2" />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Prognoză cerere */}
      {fc && fc.method !== 'no_data' && (
        <Card>
          <CardTitle>
            Prognoză Cerere — {fc.horizon_days} zile
            <span className="ml-3 text-xs text-gray-500 normal-case font-normal">
              metodă: {METHOD_LABEL[fc.method] ?? fc.method}
            </span>
          </CardTitle>
          <div className="flex gap-6 mb-3 text-sm">
            <div>
              <span className="text-gray-500">Total prognoză </span>
              <span className="text-white font-medium tabular-nums">{fc.total_forecast.toFixed(0)} unități</span>
            </div>
            <div>
              <span className="text-gray-500">Interval 80%: </span>
              <span className="text-gray-400 tabular-nums">{fc.total_lower.toFixed(0)} – {fc.total_upper.toFixed(0)}</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart
              data={fc.weeks.map(w => ({
                week: w.week_start.slice(5),  // MM-DD
                forecast: w.forecast,
                lower: w.lower,
                band: w.upper - w.lower,
              }))}
              margin={{ left: 0, right: 12, top: 5, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="week" tick={{ fill: '#6b7280', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(v: number, name: string) => {
                  if (name === 'band') return null
                  if (name === 'lower') return null
                  return [v.toFixed(1), name === 'forecast' ? 'Prognoză' : name]
                }}
              />
              <Area dataKey="lower" stackId="pi" stroke="none" fill="transparent" legendType="none" />
              <Area dataKey="band"  stackId="pi" stroke="none" fill="#3b82f6" fillOpacity={0.15} name="Interval 80%" />
              <Line dataKey="forecast" stroke="#60a5fa" dot={false} strokeWidth={2} name="Prognoză" />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Punct de reaprovizionare */}
        <Card>
          <CardTitle>Punct de Reaprovizionare</CardTitle>
          <div className="space-y-3 text-sm">
            {[
              { label: 'Punct Reaprovizionare (ROP)', value: p.rop?.toFixed(0) + ' unități' },
              { label: 'Stoc de Siguranță',           value: p.safety_stock?.toFixed(0) + ' unități' },
              { label: 'Cantitate Recomandată',        value: `${p.suggested_order_qty} unități` },
              { label: 'Cost Estimat Comandă',         value: p.estimated_cost_ron ? RON(p.estimated_cost_ron) : '—' },
              { label: 'Zile până la ROP',             value: p.days_until_rop ? `${p.days_until_rop.toFixed(0)} zile` : 'Deja sub ROP' },
            ].map(({ label, value }) => (
              <div key={label} className="flex justify-between">
                <span className="text-gray-500">{label}</span>
                <span className="text-white font-medium">{value ?? '—'}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Furnizor + sezonalitate */}
        <div className="space-y-4">
          {p.supplier && (
            <Card>
              <CardTitle>Furnizor</CardTitle>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Nume</span>
                  <span className="text-white font-medium">{p.supplier.supplier_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Timp livrare</span>
                  <span className="text-white font-medium">{p.supplier.lead_time_days} zile</span>
                </div>
              </div>
            </Card>
          )}

          <Card>
            <CardTitle>
              Sezonalitate {p.is_seasonal && <span className="ml-2 text-yellow-400 text-xs font-normal normal-case">sezonier</span>}
            </CardTitle>
            {p.seasonal_note && <p className="text-xs text-yellow-300 mb-3">{p.seasonal_note}</p>}
            <div className="flex items-end gap-0.5 h-16">
              {seasonData.map(({ month, index }) => {
                const pct = Math.min(100, (index / 2) * 100)
                const color = index >= 1.4 ? 'bg-yellow-400' : index <= 0.6 ? 'bg-gray-600' : 'bg-blue-500'
                return (
                  <div key={month} className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full flex flex-col justify-end h-12">
                      <div className={`w-full rounded-sm ${color}`} style={{ height: `${pct}%` }} title={`${month}: ${index}x`} />
                    </div>
                    <span className="text-xs text-gray-600">{month}</span>
                  </div>
                )
              })}
            </div>
          </Card>
        </div>
      </div>

      {/* Detalii cerere */}
      <Card>
        <CardTitle>Detalii Cerere</CardTitle>
        <div className="grid grid-cols-4 gap-4 text-sm">
          {[
            { label: 'Cerere zilnică',    value: `${p.daily_demand.toFixed(2)} unități/zi` },
            { label: 'Deviație standard', value: `±${p.std_dev_daily.toFixed(2)} unități/zi` },
            { label: 'Tendință',          value: <span className="flex items-center gap-1"><TrendArrow trend={p.trend} />{TREND_LABEL[p.trend] ?? p.trend} ({p.trend_pct >= 0 ? '+' : ''}{(p.trend_pct * 100).toFixed(1)}%)</span> },
            { label: 'Tendință marjă',    value: p.margin_trend ? (MARGIN_TREND_LABEL[p.margin_trend] ?? p.margin_trend) : '—' },
          ].map(({ label, value }) => (
            <div key={label}>
              <p className="text-gray-500 mb-0.5">{label}</p>
              <p className="text-white font-medium">{value}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
