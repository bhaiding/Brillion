import { FormEvent, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, tokenKey } from '../api'
import { Logo } from '../components/Logo'

export function JoinPage() {
  const { code = '' } = useParams()
  const navigate = useNavigate()
  const [nickname, setNickname] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const existing = localStorage.getItem(tokenKey(code, 'player'))

  const join = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const result = await api.join(code, nickname)
      localStorage.setItem(tokenKey(code, 'player'), result.token)
      localStorage.setItem(`brillion:${code}:player-id`, result.player_id)
      navigate(`/room/${code}/play`)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not join') }
    finally { setBusy(false) }
  }
  return (
    <main className="grid min-h-[100dvh] place-items-center bg-electric p-5 noise">
      <section className="card w-full max-w-md p-7 sm:p-9">
        <Logo />
        <p className="mt-10 text-sm font-bold uppercase tracking-[.16em] text-electric">Joining room</p>
        <h1 className="mt-1 font-display text-5xl font-extrabold tracking-[.08em]">{code.toUpperCase()}</h1>
        {existing ? (
          <div className="mt-8"><p className="mb-4 text-slate-600">You already have a seat in this room.</p><button className="btn-primary w-full" onClick={() => navigate(`/room/${code}/play`)}>Reconnect <ArrowRight /></button></div>
        ) : (
          <form onSubmit={join} className="mt-8 space-y-4">
            <label className="block font-bold" htmlFor="nickname">What should we call you?</label>
            <input id="nickname" className="field" value={nickname} onChange={(e) => setNickname(e.target.value.slice(0, 24))} placeholder="Your nickname" autoComplete="nickname" autoFocus required />
            <button className="btn-primary w-full" disabled={busy || !nickname.trim()}>{busy ? 'Joining…' : 'Join the game'} <ArrowRight /></button>
            {error && <p className="font-semibold text-red-600" role="alert">{error}</p>}
          </form>
        )}
      </section>
    </main>
  )
}

