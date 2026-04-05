const VARIANTS: Record<string, string> = {
  OK:         'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  Watch:      'bg-yellow-900/50 text-yellow-300 border border-yellow-700',
  OrderNow:   'bg-orange-900/50 text-orange-300 border border-orange-700',
  Critical:   'bg-red-900/50 text-red-300 border border-red-700',
  Dead:       'bg-gray-800 text-gray-400 border border-gray-600',
  Declining:  'bg-purple-900/50 text-purple-300 border border-purple-700',
  // generic colours
  green:  'bg-emerald-900/50 text-emerald-300 border border-emerald-700',
  amber:  'bg-yellow-900/50 text-yellow-300 border border-yellow-700',
  red:    'bg-red-900/50 text-red-300 border border-red-700',
  gray:   'bg-gray-800 text-gray-400 border border-gray-600',
}

// Display labels — internal codes rămân în engleză pentru logica de sortare/filtrare
const LABELS: Record<string, string> = {
  OK:       'Normal',
  Watch:    'Atenție',
  OrderNow: 'Comandă Acum',
  Critical: 'Critic',
  Dead:     'Stoc Mort',
  Declining: 'Vol. Scăzut',   // volum vânzări scăzut față de perioada anterioară
}

export function Badge({ label, variant }: { label: string; variant?: string }) {
  const cls = VARIANTS[variant ?? label] ?? VARIANTS.gray
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {LABELS[label] ?? label}
    </span>
  )
}
