import type { RoomSettings, RoomState } from './types'

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_URL}/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Something went wrong' }))
    throw new ApiError(response.status, body.detail ?? 'Something went wrong')
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export const tokenKey = (code: string, role: 'host' | 'player') => `brillion:${code.toUpperCase()}:${role}`

export const api = {
  async create(nickname: string, settings?: Partial<RoomSettings>) {
    return request<{ room_code: string; token: string; role: 'host'; player_id: string }>('/rooms', {
      method: 'POST',
      body: JSON.stringify({ nickname, settings: settings ?? {} }),
    })
  },
  async join(code: string, nickname: string) {
    return request<{ room_code: string; token: string; role: 'player'; player_id: string }>(
      `/rooms/${code}/join`,
      { method: 'POST', body: JSON.stringify({ nickname }) },
    )
  },
  state: (code: string, token: string) => request<RoomState>(`/rooms/${code}/state`, {}, token),
  start: (code: string, token: string) => request<RoomState>(`/rooms/${code}/start`, { method: 'POST' }, token),
  advance: (code: string, token: string, stateVersion: number) =>
    request<RoomState>(`/rooms/${code}/advance`, {
      method: 'POST',
      body: JSON.stringify({ expected_state_version: stateVersion }),
    }, token),
  submit: (code: string, token: string, answer: string) =>
    request<{ accepted: boolean; locked: boolean; message: string; canonical_answer: string | null }>(
      `/rooms/${code}/answers`,
      { method: 'POST', body: JSON.stringify({ answer }) },
      token,
    ),
  removePlayer: (code: string, token: string, playerId: string) =>
    request<void>(`/rooms/${code}/players/${playerId}`, { method: 'DELETE' }, token),
  rematch: (code: string, token: string) => request<RoomState>(`/rooms/${code}/rematch`, { method: 'POST' }, token),
  claimHost: (code: string, token: string) =>
    request<{ room_code: string; token: string; role: 'host'; player_id: string }>(`/rooms/${code}/claim-host`, { method: 'POST' }, token),
  updateSettings: (code: string, token: string, settings: RoomSettings) =>
    request<RoomState>(`/rooms/${code}/settings`, {
      method: 'PATCH',
      body: JSON.stringify({ settings }),
    }, token),
}

export function websocketUrl(code: string, token: string) {
  const base = API_URL || window.location.origin
  const url = new URL(`${base}/api/rooms/${code}/ws`)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.searchParams.set('token', token)
  return url.toString()
}
