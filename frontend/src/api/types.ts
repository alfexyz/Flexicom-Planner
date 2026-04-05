export interface OverviewResponse {
  revenue: {
    this_month: number
    last_month: number
    same_month_last_year: number
    trend_pct: number | null
  }
  inventory: {
    total_ron: number
    healthy_ron: number
    slow_ron: number
    critical_ron: number
    dead_ron: number
    healthy_pct: number
    slow_pct: number
    critical_pct: number
    dead_pct: number
  }
  alert_counts: {
    critical: number
    order_now: number
    watch: number
    dead_stock: number
    declining: number
    customer_deviation: number
    total: number
  }
  top_alerts: AlertEntry[]
}

export interface AlertEntry {
  product_code: string
  product_name: string
  days_of_cover: number | null
  message: string
}

export interface ProductSummary {
  product_code: string
  product_name: string
  current_stock: number
  days_of_cover: number | null
  days_of_cover_adjusted: number | null
  color: 'green' | 'amber' | 'red'
  daily_demand: number
  weekly_demand: number
  trend: 'rising' | 'flat' | 'falling'
  margin_pct: number | null
  status: 'OK' | 'Watch' | 'OrderNow' | 'Critical' | 'Dead' | 'Declining'
}

export interface ProductDetail {
  product_code: string
  product_name: string
  current_stock: number
  days_of_cover: number | null
  days_of_cover_adjusted: number | null
  color: string
  seasonal_note: string | null
  rop: number | null
  safety_stock: number | null
  suggested_order_qty: number | null
  below_rop: boolean | null
  days_until_rop: number | null
  estimated_cost_ron: number | null
  lead_time_days: number | null
  daily_demand: number
  weekly_demand: number
  std_dev_daily: number
  trend: string
  trend_pct: number
  is_seasonal: boolean
  seasonality_indices: Record<string, number>
  peak_month: number
  trough_month: number
  current_margin_pct: number | null
  avg_margin_pct: number | null
  margin_trend: string | null
  cost_increase_alert: boolean | null
  cost_increase_pct: number | null
  monthly_margin_history: Array<{
    month: string
    avg_sell_price: number
    avg_buy_price: number | null
    margin_pct: number | null
  }>
  supplier: {
    supplier_cui: string
    supplier_name: string
    lead_time_days: number
  } | null
}

export interface AlertsResponse {
  critical: AlertEntry[]
  order_now: AlertEntry[]
  watch: AlertEntry[]
  dead_stock: DeadStockEntry[]
  declining: DecliningEntry[]
  customer_deviation: CustomerDeviationAlert[]
}

export interface DeadStockEntry {
  product_code: string
  product_name: string
  quantity_in_stock: number
  units_sold_in_period: number
  capital_trapped: number
  last_sale_date: string | null
}

export interface DecliningEntry {
  product_code: string
  product_name: string
  recent_daily: number
  previous_daily: number
  decline_pct: number
  is_seasonal: boolean
  status: string
}

export interface CustomerDeviationAlert {
  customer_cui: string
  customer_name: string
  avg_order_gap_days: number | null
  last_order_date: string | null
  days_since_last_order: number | null
  days_overdue: number | null
  status: string
}

export interface ForecastWeek {
  week_start: string
  week_end: string
  forecast: number
  lower: number
  upper: number
}

export interface ForecastResponse {
  product_code: string
  method: 'xgboost' | 'croston' | 'trend_seasonal' | 'no_data'
  horizon_days: number
  as_of: string
  weeks: ForecastWeek[]
  total_forecast: number
  total_lower: number
  total_upper: number
}

export interface CustomerSummary {
  customer_cui: string
  customer_name: string
  avg_order_gap_days: number | null
  last_order_date: string | null
  days_since_last_order: number | null
  days_overdue: number | null
  status: string
  confidence: string
  total_orders: number | null
}
