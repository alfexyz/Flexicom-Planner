import { NavLink, Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from './api/client'
import Overview     from './pages/Overview'
import ProductList  from './pages/ProductList'
import ProductDetail from './pages/ProductDetail'
import Alerts       from './pages/Alerts'

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
          isActive ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white'
        }`
      }
    >
      {label}
    </NavLink>
  )
}

function AlertBadge() {
  const { data } = useQuery({ queryKey: ['overview'], queryFn: api.overview, staleTime: 60_000 })
  const total = data?.alert_counts.total ?? 0
  if (!total) return null
  return (
    <span className="ml-1.5 bg-red-600 text-white text-xs font-bold px-1.5 py-0.5 rounded-full">
      {total}
    </span>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-950">
      {/* Top nav */}
      <nav className="border-b border-gray-800 bg-gray-950 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-2">
          <span className="text-white font-bold text-base mr-6">Flexicom Planner</span>
          <NavItem to="/"          label="Prezentare Generală" />
          <NavItem to="/products"  label="Produse" />
          <NavLink
            to="/alerts"
            className={({ isActive }) =>
              `px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center ${
                isActive ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white'
              }`
            }
          >
            Alerte <AlertBadge />
          </NavLink>
        </div>
      </nav>

      {/* Page content */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        <Routes>
          <Route path="/"                    element={<Overview />} />
          <Route path="/products"            element={<ProductList />} />
          <Route path="/products/:code"      element={<ProductDetail />} />
          <Route path="/alerts"              element={<Alerts />} />
        </Routes>
      </main>
    </div>
  )
}
