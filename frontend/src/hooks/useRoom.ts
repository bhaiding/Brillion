import { useCallback, useEffect, useRef, useState } from 'react'
import { api, websocketUrl } from '../api'
import type { RoomState } from '../types'

export function useRoom(code: string, token: string | null) {
  const [state, setState] = useState<RoomState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'reconnecting' | 'offline'>('connecting')
  const reconnectAttempt = useRef(0)
  const stopped = useRef(false)

  const refresh = useCallback(async () => {
    if (!token) return
    try {
      const next = await api.state(code, token)
      setState(next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the room')
    }
  }, [code, token])

  useEffect(() => {
    if (!token) return
    stopped.current = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let pingTimer: number | null = null

    const connect = () => {
      setConnection(reconnectAttempt.current ? 'reconnecting' : 'connecting')
      socket = new WebSocket(websocketUrl(code, token))
      socket.onopen = () => {
        reconnectAttempt.current = 0
        setConnection('connected')
        refresh()
        pingTimer = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ping' }))
        }, 15_000)
      }
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as { type?: string }
        if (message.type === 'state_changed' || message.type === 'connected') refresh()
      }
      socket.onclose = () => {
        if (pingTimer) window.clearInterval(pingTimer)
        if (stopped.current) return
        setConnection(navigator.onLine ? 'reconnecting' : 'offline')
        const delay = Math.min(15_000, 500 * 2 ** reconnectAttempt.current) + Math.random() * 300
        reconnectAttempt.current += 1
        reconnectTimer = window.setTimeout(connect, delay)
      }
    }
    connect()
    return () => {
      stopped.current = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (pingTimer) window.clearInterval(pingTimer)
      socket?.close()
    }
  }, [code, token, refresh])

  return { state, setState, error, connection, refresh }
}

