import { useCallback, useState } from 'react'

export function useSound() {
  const [muted, setMuted] = useState(() => localStorage.getItem('brillion:muted') === 'true')
  const play = useCallback((kind: 'submit' | 'tick' | 'reveal') => {
    if (muted) return
    const AudioContextClass = window.AudioContext
    const context = new AudioContextClass()
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    oscillator.frequency.value = kind === 'submit' ? 660 : kind === 'reveal' ? 520 : 340
    gain.gain.setValueAtTime(0.08, context.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.16)
    oscillator.connect(gain).connect(context.destination)
    oscillator.start()
    oscillator.stop(context.currentTime + 0.16)
  }, [muted])
  const toggle = () => setMuted((value) => {
    localStorage.setItem('brillion:muted', String(!value))
    return !value
  })
  return { muted, toggle, play }
}

