import { Check, Circle, Trash2, WifiOff } from 'lucide-react'
import type { Player } from '../types'

export function PlayerList({ players, onRemove, answering = false }: { players: Player[]; onRemove?: (id: string) => void; answering?: boolean }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {players.map((player) => (
        <div key={player.id} className="flex items-center gap-3 rounded-2xl border-2 border-ink bg-white px-4 py-3 shadow-[3px_3px_0_#141128]">
          {answering ? (player.submitted ? <Check className="text-emerald-600" /> : <Circle className="text-slate-300" />) : player.connected ? <span className="h-3 w-3 rounded-full bg-emerald-500" /> : <WifiOff className="text-slate-400" size={18} />}
          <span className="min-w-0 flex-1 truncate font-bold">{player.nickname}</span>
          {onRemove && <button onClick={() => onRemove(player.id)} className="rounded-lg p-1 text-slate-500 hover:bg-red-50 hover:text-red-600" aria-label={`Remove ${player.nickname}`}><Trash2 size={18} /></button>}
        </div>
      ))}
    </div>
  )
}

