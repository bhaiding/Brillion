import { FormEvent, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle2, Copy, Send, Trash2, Volume2, VolumeX } from 'lucide-react'
import { Navigate, useParams } from 'react-router-dom'
import { api, tokenKey } from '../api'
import { ConnectionBanner } from '../components/ConnectionBanner'
import { Countdown } from '../components/Countdown'
import { Leaderboard } from '../components/Leaderboard'
import { Logo } from '../components/Logo'
import { RarityBadge } from '../components/RarityBadge'
import { useRoom } from '../hooks/useRoom'
import { useSound } from '../hooks/useSound'

export function PlayPage() {
  const { code = '' } = useParams()
  const hostToken = localStorage.getItem(tokenKey(code, 'host'))
  const token = localStorage.getItem(tokenKey(code, 'player')) ?? hostToken
  const isHost = Boolean(hostToken && token === hostToken)
  const playerId = localStorage.getItem(`brillion:${code}:player-id`) ?? undefined
  const { state, setState, error, connection } = useRoom(code, token)
  const { muted, toggle, play } = useSound()
  const [answer, setAnswer] = useState('')
  const [locked, setLocked] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const round = state?.round_number
  useEffect(() => { setAnswer(''); setLocked(false); setFeedback('') }, [round])
  const me = useMemo(() => state?.players.find((p) => p.id === playerId), [state, playerId])
  if (!token) return <Navigate to={`/room/${code}`} replace />
  if (!state) return <main className="grid min-h-[100dvh] place-items-center bg-cream p-5"><div className="text-center"><Logo /><p className="mt-5 font-bold">{error ?? 'Rejoining your game…'}</p></div></main>
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!answer.trim() || locked) return
    setBusy(true); setFeedback('')
    try {
      const result = await api.submit(code, token, answer)
      setFeedback(result.message)
      if (result.accepted) { setLocked(true); play('submit') }
    } catch (err) { setFeedback(err instanceof Error ? err.message : 'Could not submit') }
    finally { setBusy(false) }
  }
  const myResult = state.results?.find((result) => result.player_id === playerId)
  const hostPlayer = state.players.find((player) => player.id === state.host_player_id)
  const hostAction = async (action: () => Promise<typeof state>) => {
    setBusy(true); setActionError('')
    try { setState(await action()) } catch (err) { setActionError(err instanceof Error ? err.message : 'Action failed') }
    finally { setBusy(false) }
  }
  const recoverHost = async () => {
    if (!token) return
    setBusy(true); setActionError('')
    try {
      const result = await api.claimHost(code, token)
      localStorage.setItem(tokenKey(code, 'host'), result.token)
      window.location.reload()
    } catch (err) { setActionError(err instanceof Error ? err.message : 'Could not recover creator controls') }
    finally { setBusy(false) }
  }
  return (
    <main className="min-h-[100dvh] bg-cream px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-5 noise">
      <ConnectionBanner status={connection} />
      <header className="mx-auto flex max-w-xl items-center justify-between"><Logo /><button onClick={toggle} className="rounded-xl border-2 border-ink bg-white p-2" aria-label={muted ? 'Unmute' : 'Mute'}>{muted ? <VolumeX size={20} /> : <Volume2 size={20} />}</button></header>
      <section className="mx-auto mt-7 max-w-xl">
        {state.state === 'LOBBY' && <div className="card"><div className="text-center"><div className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-full bg-mint"><CheckCircle2 size={34} /></div><h1 className="font-display text-3xl font-extrabold">You're in, {me?.nickname}.</h1><p className="mt-3 text-slate-600">Share this code so friends can join on their phones.</p><button className="mx-auto mt-6 flex items-center gap-3 rounded-2xl border-2 border-ink bg-sun px-5 py-3 font-display text-3xl font-extrabold tracking-[.14em] shadow-[3px_3px_0_#141128]" onClick={() => navigator.clipboard.writeText(state.room_code)}>{state.room_code} <Copy size={20} /></button></div><div className="mt-8 space-y-2">{state.players.map((player) => <div key={player.id} className="flex items-center gap-3 rounded-2xl border-2 border-ink bg-white p-3"><span className={`h-3 w-3 rounded-full ${player.connected ? 'bg-emerald-500' : 'bg-slate-300'}`} /><span className="flex-1 font-bold">{player.nickname}{player.id === state.players.find((p) => p.id === playerId)?.id && ' (you)'}</span>{isHost && player.id !== playerId && <button onClick={() => hostAction(async () => { await api.removePlayer(code, token, player.id); return api.state(code, token) })} aria-label={`Remove ${player.nickname}`}><Trash2 size={18} /></button>}</div>)}</div>{isHost ? <button className="btn-primary mt-7 w-full" disabled={busy || state.players.length < 1} onClick={() => hostAction(() => api.start(code, token))}>Start game</button> : <p className="mt-6 text-center font-bold text-slate-500">Waiting for the party creator…</p>}</div>}
        {state.state === 'QUESTION_PREVIEW' && <div className="card"><p className="font-bold uppercase tracking-[.14em] text-electric">Question {state.round_number} of {state.question_count} · {state.question?.category}</p><h1 className="mt-4 font-display text-4xl font-extrabold leading-tight">{state.question?.text}</h1><p className="mt-5 text-slate-600">{state.question?.eligibility_criteria}</p>{isHost ? <button className="btn-primary mt-8 w-full" disabled={busy} onClick={() => hostAction(() => api.advance(code, token, state.state_version))}>Start 25-second timer</button> : <div className="mt-8 rounded-2xl bg-mint p-4 text-center font-bold">Get ready…</div>}</div>}
        {state.state === 'ANSWERING' && <div className="card !p-5 sm:!p-7"><div className="flex items-start gap-4"><div className="min-w-0 flex-1"><p className="text-sm font-bold uppercase tracking-[.12em] text-electric">Question {state.round_number} of {state.question_count}</p><h1 className="mt-2 font-display text-3xl font-extrabold leading-tight">{state.question?.text}</h1></div><Countdown deadline={state.deadline_at} serverTime={state.server_time} /></div><form className="mt-7" onSubmit={submit}><label htmlFor="answer" className="mb-2 block font-bold">Your answer</label><div className="flex gap-2"><input id="answer" className="field min-w-0" value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={locked} autoFocus autoComplete="off" enterKeyHint="send" placeholder="Type something clever…" /><button className="btn-primary !px-4" disabled={busy || locked || !answer.trim()} aria-label="Submit answer"><Send /></button></div>{feedback && <p className={`mt-3 font-bold ${locked ? 'text-emerald-700' : 'text-red-600'}`} role="status">{feedback}</p>}{locked && <div className="mt-5 flex items-center gap-3 rounded-2xl border-2 border-ink bg-mint p-4"><CheckCircle2 /><strong>Locked in. No peeking at anyone else.</strong></div>}</form></div>}
        {(state.state === 'SCORING') && <div className="card text-center"><h1 className="font-display text-4xl font-extrabold">Pens down!</h1><p className="mt-3 text-slate-600">Checking every answer…</p></div>}
        {state.state === 'REVEAL' && <motion.div initial={{ opacity: 0, scale: .96 }} animate={{ opacity: 1, scale: 1 }}><p className="font-bold uppercase tracking-[.14em] text-electric">Everyone's answers</p><h1 className="mt-1 font-display text-4xl font-extrabold">The reveal</h1><div className="mt-6 space-y-3">{state.results?.map((result, index) => <motion.article key={result.player_id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .1 }} className={`rounded-3xl border-2 border-ink p-4 shadow-[3px_3px_0_#141128] ${result.player_id === playerId ? 'bg-mint' : 'bg-white'}`}><div className="flex items-center justify-between gap-2"><strong>{result.nickname}{result.player_id === playerId && ' (you)'}</strong><span className="font-display text-2xl font-extrabold">+{result.points}</span></div><p className="my-2 font-display text-2xl font-extrabold">{result.raw_answer || 'No answer'}</p>{result.tier ? <RarityBadge tier={result.tier} /> : <span className="font-bold text-red-600">No match</span>}{result.interesting_fact && <p className="mt-3 text-sm text-slate-600">{result.interesting_fact}</p>}</motion.article>)}</div>{isHost ? <button className="btn-primary mt-7 w-full" disabled={busy} onClick={() => hostAction(() => api.advance(code, token, state.state_version))}>Show leaderboard</button> : <p className="mt-6 text-center font-bold text-slate-500">Leaderboard coming up…</p>}</motion.div>}
        {state.state === 'LEADERBOARD' && <div><p className="font-bold uppercase tracking-[.14em] text-electric">Standings</p><h1 className="mt-1 font-display text-4xl font-extrabold">After {state.round_number} questions</h1><div className="mt-6"><Leaderboard entries={state.leaderboard ?? []} currentPlayerId={playerId} /></div>{isHost ? <button className="btn-primary mt-7 w-full" disabled={busy} onClick={() => hostAction(() => api.advance(code, token, state.state_version))}>{state.round_number === state.question_count ? 'See final results' : 'Next question'}</button> : <p className="mt-6 text-center font-bold text-slate-500">Waiting for the party creator…</p>}</div>}
        {state.state === 'FINISHED' && <div className="text-center"><p className="font-bold uppercase tracking-[.14em] text-electric">Game over</p><h1 className="mt-2 font-display text-5xl font-extrabold">{state.leaderboard?.[0]?.nickname} wins!</h1><div className="mt-7 text-left"><Leaderboard entries={state.leaderboard ?? []} currentPlayerId={playerId} /></div>{isHost ? <button className="btn-primary mt-7 w-full" disabled={busy} onClick={() => hostAction(() => api.rematch(code, token))}>Play a rematch</button> : <p className="mt-7 font-bold text-slate-500">The party creator can start a rematch.</p>}</div>}
        {!isHost && hostPlayer && !hostPlayer.connected && <button className="btn-secondary mt-7 w-full" disabled={busy} onClick={recoverHost}>Recover party controls</button>}
        {actionError && <p className="mt-5 text-center font-bold text-red-600" role="alert">{actionError}</p>}
      </section>
    </main>
  )
}
