import type { RarityTier } from '../types'

const names: Record<RarityTier, string> = {
  common: 'Common', predictably_obscure: 'Predictably obscure', uncommon: 'Uncommon',
  rare: 'Rare', deep_cut: 'Deep cut', brillion: 'Brillion!',
}
const colors: Record<RarityTier, string> = {
  common: 'bg-slate-200', predictably_obscure: 'bg-sky-200', uncommon: 'bg-mint',
  rare: 'bg-sun', deep_cut: 'bg-orange-300', brillion: 'bg-electric text-white',
}

export function RarityBadge({ tier }: { tier: RarityTier }) {
  return <span className={`inline-flex rounded-full border-2 border-ink px-3 py-1 text-xs font-bold uppercase tracking-wide ${colors[tier]}`}>{names[tier]}</span>
}

