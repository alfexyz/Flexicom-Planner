import type {
  AlertsResponse, CustomerSummary, ForecastResponse, OverviewResponse,
  ProductDetail, ProductSummary,
} from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  overview:    ()   => get<OverviewResponse>('/overview'),
  products:    ()   => get<ProductSummary[]>('/products'),
  product:     (id: string) => get<ProductDetail>(`/products/${id}`),
  forecast:    (id: string, days = 90) => get<ForecastResponse>(`/products/${id}/forecast?days=${days}`),
  alerts:      ()   => get<AlertsResponse>('/alerts'),
  customers:   ()   => get<CustomerSummary[]>('/customers'),
  exportOrders: () => `${BASE}/alerts/orders/export`,
}
