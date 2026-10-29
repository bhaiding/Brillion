export type GameState =
  | 'LOBBY'
  | 'QUESTION_PREVIEW'
  | 'ANSWERING'
  | 'SCORING'
  | 'REVEAL'
  | 'LEADERBOARD'
  | 'FINISHED'

export type RarityTier =
  | 'common'
  | 'predictably_obscure'
  | 'uncommon'
  | 'rare'
  | 'deep_cut'
  | 'brillion'

export interface RoomSettings {
  question_count: number
  answer_seconds: number
  categories: string[]
  family_friendly: boolean
  hide_leaderboard: boolean
  host_controlled_transitions: boolean
  automatic_transition_seconds: number
}

export interface Player {
  id: string
  nickname: string
  connected: boolean
  submitted: boolean
  score: number
}

export interface LeaderboardEntry {
  rank: number
  player_id: string
  nickname: string
  score: number
}

export interface AnswerResult {
  player_id: string
  nickname: string
  raw_answer: string | null
  canonical_answer: string | null
  valid: boolean
  points: number
  tier: RarityTier | null
  total_score: number
  interesting_fact: string | null
}

export interface RoomState {
  server_time: string
  room_code: string
  state: GameState
  state_version: number
  host_player_id: string | null
  settings: RoomSettings
  players: Player[]
  game_id: string | null
  round_index: number | null
  round_number: number | null
  question_count: number
  question: { text: string; category: string; eligibility_criteria: string } | null
  deadline_at: string | null
  results: AnswerResult[] | null
  leaderboard: LeaderboardEntry[] | null
  final_answers: Record<string, Array<Record<string, string | number | null>>> | null
}
