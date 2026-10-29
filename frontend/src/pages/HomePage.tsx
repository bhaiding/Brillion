import { FormEvent, useState } from 'react'
import { ArrowRight, Gem, Timer, Users } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, tokenKey } from '../api'
import { Logo } from '../components/Logo'

export function HomePage() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [nickname, setNickname] = useState('')
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const create = async (event?: FormEvent) => {
    event?.preventDefault()
    if (!creating) { setCreating(true); return }
    if (!nickname.trim()) { setError('Enter your nickname to create the party'); return }
    setBusy(true); setError('')
    try {
      const result = await api.create(nickname)
      localStorage.setItem(tokenKey(result.room_code, 'host'), result.token)
      localStorage.setItem(`brillion:${result.room_code}:player-id`, result.player_id)
      navigate(`/room/${result.room_code}/play`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create a game')
    } finally { setBusy(false) }
  }

  const join = (event: FormEvent) => {
    event.preventDefault()
    const clean = code.trim().toUpperCase()
    if (clean.length < 4) return setError('Enter the room code shown on the big screen')
    navigate(`/room/${clean}`)
  }

  return (
    <main className="min-h-screen overflow-hidden bg-cream noise">
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-6 sm:px-8">
        <Logo />
        <a href="#how" className="hidden font-bold hover:underline sm:block">How it works</a>
      </nav>
      <section className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 pb-20 pt-10 sm:px-8 lg:grid-cols-[1.15fr_.85fr] lg:py-24">
        <div className="relative z-10">
          <div className="mb-5 inline-flex rotate-[-2deg] items-center gap-2 rounded-full border-2 border-ink bg-mint px-4 py-2 text-sm font-bold shadow-[3px_3px_0_#141128]">
            <Gem size={17} /> Rare answers win
          </div>
          <h1 className="max-w-3xl font-display text-6xl font-extrabold leading-[.92] tracking-[-.065em] sm:text-7xl lg:text-[6.7rem]">
            Think beyond the <span className="text-electric">obvious.</span>
          </h1>
          <p className="mt-7 max-w-xl text-lg leading-relaxed text-slate-700 sm:text-xl">
            Seven open-ended questions. Twenty-five seconds each. Correct answers score—but the answers fewer people think of score bigger.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            {creating ? <form onSubmit={create} className="flex min-w-0 gap-2"><input className="field min-w-0 sm:w-48" value={nickname} onChange={(e) => setNickname(e.target.value.slice(0, 24))} placeholder="Your nickname" autoFocus /><button className="btn-primary whitespace-nowrap" disabled={busy}>{busy ? 'Creating…' : 'Create'}</button></form> : <button className="btn-primary text-lg" onClick={() => create()} disabled={busy}>Create game <ArrowRight /></button>}
            <form onSubmit={join} className="flex min-w-0 gap-2">
              <label className="sr-only" htmlFor="room-code">Room code</label>
              <input id="room-code" className="field w-40 uppercase tracking-[.18em]" value={code} onChange={(e) => setCode(e.target.value.replace(/[^a-z0-9]/gi, '').slice(0, 8))} placeholder="CODE" autoCapitalize="characters" />
              <button className="btn-secondary" type="submit">Join</button>
            </form>
          </div>
          {error && <p className="mt-4 font-semibold text-red-600" role="alert">{error}</p>}
        </div>
        <div className="relative mx-auto w-full max-w-lg">
          <div className="absolute -left-8 -top-8 h-32 w-32 rotate-12 rounded-[2rem] border-2 border-ink bg-sun" />
          <div className="absolute -bottom-8 -right-8 h-40 w-40 -rotate-6 rounded-full border-2 border-ink bg-coral" />
          <div className="card relative rotate-[2deg] p-7 sm:p-9">
            <p className="text-sm font-bold uppercase tracking-[.16em] text-electric">Question 4 of 7</p>
            <h2 className="mt-4 font-display text-3xl font-extrabold leading-tight sm:text-4xl">Name a country that shares a border with Germany.</h2>
            <div className="mt-7 space-y-3">
              {[['France', '10', 'bg-slate-200'], ['Czechia', '60', 'bg-sun'], ['Luxembourg', '100', 'bg-electric text-white']].map(([answer, points, color]) => (
                <div key={answer} className={`flex items-center rounded-2xl border-2 border-ink p-4 ${color}`}><span className="flex-1 font-bold">{answer}</span><strong className="font-display text-2xl">+{points}</strong></div>
              ))}
            </div>
          </div>
        </div>
      </section>
      <section id="how" className="border-y-2 border-ink bg-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-16 sm:px-8 md:grid-cols-3">
          {[[Users, 'Gather your crew', 'Create a party, share its code, and let everyone join from their own phone.'], [Timer, 'Answer together', 'Everyone gets the same prompt and 25 seconds to lock in one valid answer.'], [Gem, 'Reveal the deep cuts', "Every phone reveals the party's answers and points, followed by the leaderboard."]].map(([Icon, title, copy], index) => {
            const C = Icon as typeof Users
            return <article key={String(title)}><div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border-2 border-ink bg-mint shadow-[3px_3px_0_#141128]"><C /></div><p className="text-sm font-bold text-electric">0{index + 1}</p><h2 className="mt-1 font-display text-2xl font-extrabold">{String(title)}</h2><p className="mt-2 leading-relaxed text-slate-600">{String(copy)}</p></article>
          })}
        </div>
      </section>
      <footer className="mx-auto flex max-w-7xl items-center justify-between px-5 py-8 text-sm text-slate-600 sm:px-8"><Logo compact /><span>Seven questions. Infinite bragging rights.</span></footer>
    </main>
  )
}
