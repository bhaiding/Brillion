import { FormEvent, useEffect, useState } from 'react'
import { Logo } from '../components/Logo'

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''
type Question = { id: string; slug: string; category: string; review_status: string; versions: number }

export function AdminPage() {
  const [secret, setSecret] = useState(() => sessionStorage.getItem('brillion:admin-secret') ?? '')
  const [questions, setQuestions] = useState<Question[]>([])
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('Geography')
  const [count, setCount] = useState(5)
  const load = async (adminSecret = secret) => {
    if (!adminSecret) return
    const response = await fetch(`${API_URL}/api/admin/questions?search=${encodeURIComponent(search)}`, { headers: { 'X-Admin-Secret': adminSecret } })
    if (!response.ok) throw new Error(response.status === 401 ? 'Invalid admin secret' : 'Could not load questions')
    const body = await response.json(); setQuestions(body.items); setError('')
  }
  useEffect(() => { load().catch((err) => setError(err.message)) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const login = (event: FormEvent) => { event.preventDefault(); sessionStorage.setItem('brillion:admin-secret', secret); load().catch((err) => setError(err.message)) }
  const generate = async () => {
    const response = await fetch(`${API_URL}/api/admin/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': secret }, body: JSON.stringify({ category, count }) })
    const body = await response.json(); if (!response.ok) return setError(body.detail); setError(`Generation job ${body.job_id} queued for review.`)
  }
  if (!questions.length && !sessionStorage.getItem('brillion:admin-secret')) return <main className="grid min-h-screen place-items-center bg-cream p-5"><form onSubmit={login} className="card w-full max-w-md"><Logo /><h1 className="mt-8 font-display text-3xl font-extrabold">Question desk</h1><p className="mt-2 text-slate-600">Protected administration for review and publication.</p><label className="mt-6 block font-bold" htmlFor="secret">Admin secret</label><input id="secret" type="password" className="field mt-2" value={secret} onChange={(e) => setSecret(e.target.value)} /><button className="btn-primary mt-4 w-full">Sign in</button>{error && <p className="mt-3 font-bold text-red-600">{error}</p>}</form></main>
  return (
    <main className="min-h-screen bg-cream p-5 sm:p-8"><header className="mx-auto flex max-w-6xl items-center justify-between"><Logo /><span className="rounded-full bg-mint px-4 py-2 text-sm font-bold">Admin</span></header><div className="mx-auto mt-10 grid max-w-6xl gap-7 lg:grid-cols-[1fr_320px]"><section><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="font-bold uppercase tracking-[.14em] text-electric">Question bank</p><h1 className="font-display text-4xl font-extrabold">Published & in review</h1></div><form onSubmit={(e) => { e.preventDefault(); load().catch((err) => setError(err.message)) }} className="flex gap-2"><input className="field !min-h-10" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} /><button className="btn-secondary">Search</button></form></div><div className="mt-6 overflow-hidden rounded-3xl border-2 border-ink bg-white"><table className="w-full text-left"><thead className="bg-ink text-white"><tr><th className="p-4">Question</th><th className="p-4">Category</th><th className="p-4">Status</th></tr></thead><tbody>{questions.map((question) => <tr key={question.id} className="border-t border-slate-200"><td className="p-4 font-bold">{question.slug.replaceAll('-', ' ')}</td><td className="p-4">{question.category}</td><td className="p-4"><span className="rounded-full bg-mint px-3 py-1 text-xs font-bold uppercase">{question.review_status}</span></td></tr>)}</tbody></table></div></section><aside className="card h-fit"><h2 className="font-display text-2xl font-extrabold">Generate candidates</h2><p className="mt-2 text-sm text-slate-600">AI suggests structured ideas. Nothing is published until sources, answers, rarity, and review pass.</p><label className="mt-5 block font-bold">Category</label><input className="field mt-2" value={category} onChange={(e) => setCategory(e.target.value)} /><label className="mt-4 block font-bold">Count</label><input className="field mt-2" type="number" min="1" max="25" value={count} onChange={(e) => setCount(Number(e.target.value))} /><button className="btn-primary mt-5 w-full" onClick={generate}>Queue generation</button>{error && <p className="mt-4 text-sm font-bold text-electric">{error}</p>}</aside></div></main>
  )
}

