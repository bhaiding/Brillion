import { Sparkles } from 'lucide-react'

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="inline-flex items-center gap-2 font-display font-extrabold tracking-[-0.04em] text-ink">
      <span className="grid h-10 w-10 rotate-[-5deg] place-items-center rounded-xl border-2 border-ink bg-sun shadow-[3px_3px_0_#141128]">
        <Sparkles size={22} strokeWidth={2.8} />
      </span>
      {!compact && <span className="text-2xl">BRILLION</span>}
    </div>
  )
}

