import { Crown } from 'lucide-react'
import type { LeaderboardEntry } from '../types'

export function Leaderboard({ entries, currentPlayerId }: { entries: LeaderboardEntry[]; currentPlayerId?: string }) {
  return (
    <div className="space-y-2">
      {entries.map((entry) => (
        <div key={entry.player_id} className={`flex items-center gap-3 rounded-2xl border-2 border-ink px-4 py-3 ${entry.player_id === currentPlayerId ? 'bg-mint' : 'bg-white'}`}>
          <span className="w-8 font-display text-xl font-extrabold">{entry.rank === 1 ? <Crown className="text-coral" /> : entry.rank}</span>
          <span className="min-w-0 flex-1 truncate font-bold">{entry.nickname}</span>
          <span className="font-display text-xl font-extrabold tabular-nums">{entry.score}</span>
        </div>
      ))}
    </div>
  )
}

