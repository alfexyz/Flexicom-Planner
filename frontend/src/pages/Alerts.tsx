import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { AlertEntry, CustomerDeviationAlert, DeadStockEntry, DecliningEntry } from '../api/types'
import { Card } from '../components/ui/Card'
import { PageError, Spinner } from '../components/ui/Spinner'

const RON = (n: number) =>
  new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 }).format(n) + ' RON'

function Section({ title, count, color, children }: {
  title: string; count: number; color: string; children: React.ReactNode
}) {
  if (count === 0) return null
  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <h2 className={`text-sm font-semibold uppercase tracking-wider ${color}`}>{title}</h2>
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full bg-gray-800 ${color}`}>{count}</span>
      </div>
      <div className="grid gap-3">{children}</div>
    </div>
  )
}

function InventoryAlertCard({ alert, navigate }: { alert: AlertEntry; navigate: (p: string) => void }) {
  return (
    <Card className="cursor-pointer hover:bg-gray-800 transition-colors" >
      <div className="flex justify-between items-start mb-2" onClick={() => navigate(`/products/${alert.product_code}`)}>
        <div>
          <span className="font-medium text-white">{alert.product_name}</span>
          <span className="text-xs text-gray-500 ml-2">{alert.product_code}</span>
        </div>
        {alert.days_of_cover !== null && (
          <span className="text-sm font-bold text-red-400 shrink-0">{Math.round(alert.days_of_cover)}z rămase</span>
        )}
      </div>
      <p className="text-sm text-gray-400">{alert.message}</p>
    </Card>
  )
}

function DeadStockCard({ item }: { item: DeadStockEntry }) {
  return (
    <Card>
      <div className="flex justify-between items-start">
        <div>
          <span className="font-medium text-white">{item.product_name}</span>
          <span className="text-xs text-gray-500 ml-2">{item.product_code}</span>
        </div>
        <span className="text-sm font-bold text-gray-400">{RON(item.capital_trapped)} imobilizat</span>
      </div>
      <p className="text-sm text-gray-500 mt-1">
        {item.quantity_in_stock.toFixed(0)} unități în stoc · {item.units_sold_in_period.toFixed(0)} vândute în 6 luni
        {item.last_sale_date && ` · Ultima vânzare ${item.last_sale_date}`}
      </p>
    </Card>
  )
}

function DecliningCard({ item, navigate }: { item: DecliningEntry; navigate: (p: string) => void }) {
  return (
    <Card className="cursor-pointer hover:bg-gray-800 transition-colors" onClick={() => navigate(`/products/${item.product_code}`)}>
      <div className="flex justify-between items-start">
        <div>
          <span className="font-medium text-white">{item.product_name}</span>
          <span className="text-xs text-gray-500 ml-2">{item.product_code}</span>
        </div>
        <span className="text-sm font-bold text-red-400">{(item.decline_pct * 100).toFixed(0)}% scădere</span>
      </div>
      <p className="text-sm text-gray-500 mt-1">
        {item.previous_daily.toFixed(2)} → {item.recent_daily.toFixed(2)} unități/zi
        {item.is_seasonal && ' · tipar sezonier'}
      </p>
    </Card>
  )
}

const CUSTOMER_STATUS_LABEL: Record<string, string> = {
  inactive:           'inactiv',
  significantly_late: 'întârziere mare',
  late:               'întârziat',
  on_track:           'la timp',
}

function CustomerCard({ item }: { item: CustomerDeviationAlert }) {
  const statusColor = item.status === 'inactive' ? 'text-red-400' : 'text-orange-400'
  return (
    <Card>
      <div className="flex justify-between items-start">
        <div>
          <span className="font-medium text-white">{item.customer_name}</span>
          <span className="text-xs text-gray-500 ml-2">{item.customer_cui}</span>
        </div>
        <span className={`text-sm font-bold ${statusColor}`}>{CUSTOMER_STATUS_LABEL[item.status] ?? item.status}</span>
      </div>
      <p className="text-sm text-gray-500 mt-1">
        Ultima comandă: {item.last_order_date ?? '—'}
        {item.days_overdue != null && item.days_overdue > 0 && ` · ${Math.round(item.days_overdue)} zile întârziere`}
        {item.avg_order_gap_days && ` · interval mediu ${item.avg_order_gap_days.toFixed(0)}z`}
      </p>
    </Card>
  )
}

export default function Alerts() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useQuery({ queryKey: ['alerts'], queryFn: api.alerts })

  if (isLoading) return <Spinner />
  if (error || !data) return <PageError message="Eroare la încărcarea alertelor" />

  const total = data.critical.length + data.order_now.length + data.watch.length +
                data.dead_stock.length + data.declining.length + data.customer_deviation.length

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white">Alerte Inteligente</h1>
          <span className="bg-gray-800 text-gray-300 text-sm font-medium px-3 py-1 rounded-full">{total} total</span>
        </div>
        <a
          href={api.exportOrders()}
          download
          className="inline-flex items-center gap-2 bg-blue-700 hover:bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          ↓ Export Comenzi CSV
        </a>
      </div>

      {total === 0 && (
        <div className="text-center py-20 text-gray-500">Nicio alertă astăzi. Totul este în regulă.</div>
      )}

      <Section title="🔴 Critic — rupere stoc înainte de livrare" count={data.critical.length} color="text-red-400">
        {data.critical.map(a => <InventoryAlertCard key={a.product_code} alert={a} navigate={navigate} />)}
      </Section>

      <Section title="🟠 Comandă Acum — sub punctul de reaprovizionare" count={data.order_now.length} color="text-orange-400">
        {data.order_now.map(a => <InventoryAlertCard key={a.product_code} alert={a} navigate={navigate} />)}
      </Section>

      <Section title="🟡 Atenție — stoc scăzut în 2 săptămâni" count={data.watch.length} color="text-yellow-400">
        {data.watch.map(a => <InventoryAlertCard key={a.product_code} alert={a} navigate={navigate} />)}
      </Section>

      <Section title="💀 Stoc Mort — capital imobilizat" count={data.dead_stock.length} color="text-gray-400">
        {data.dead_stock.map(d => <DeadStockCard key={d.product_code} item={d} />)}
      </Section>

      <Section title="📉 Cerere în Declin" count={data.declining.length} color="text-purple-400">
        {data.declining.map(d => <DecliningCard key={d.product_code} item={d} navigate={navigate} />)}
      </Section>

      <Section title="👤 Deviere Comportament Client" count={data.customer_deviation.length} color="text-blue-400">
        {data.customer_deviation.map(c => <CustomerCard key={c.customer_cui} item={c} />)}
      </Section>
    </div>
  )
}
