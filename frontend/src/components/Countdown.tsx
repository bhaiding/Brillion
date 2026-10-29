import { useEffect, useMemo, useState } from 'react'

export function Countdown({ deadline, serverTime }: { deadline: string | null; serverTime: string }) {
  const offset = useMemo(() => new Date(serverTime).getTime() - Date.now(), [serverTime])
  const getRemaining = () => deadline ? Math.max(0, new Date(deadline).getTime() - (Date.now() + offset)) : 0
  const [remaining, setRemaining] = useState(getRemaining)
  useEffect(() => {
    setRemaining(getRemaining())
    const timer = window.setInterval(() => setRemaining(getRemaining()), 100)
    return () => window.clearInterval(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadline, offset])
  const seconds = Math.ceil(remaining / 1000)
  const percent = deadline ? Math.min(100, (remaining / 25_000) * 100) : 0
  return (
    <div className="relative grid h-24 w-24 shrink-0 place-items-center rounded-full border-[6px] border-ink bg-cream shadow-[4px_4px_0_#141128]" aria-label={`${seconds} seconds remaining`}>
      <div className="absolute inset-[-6px] rounded-full border-[6px] border-coral transition-[clip-path]" style={{ clipPath: `inset(${100 - percent}% 0 0 0)` }} />
      <span className="font-display text-4xl font-extrabold tabular-nums">{seconds}</span>
    </div>
  )
}

