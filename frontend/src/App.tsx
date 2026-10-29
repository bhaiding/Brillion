import { Navigate, Route, Routes } from 'react-router-dom'
import { HomePage } from './pages/HomePage'
import { JoinPage } from './pages/JoinPage'
import { PlayPage } from './pages/PlayPage'
import { AdminPage } from './pages/AdminPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/room/:code" element={<JoinPage />} />
      <Route path="/room/:code/play" element={<PlayPage />} />
      <Route path="/room/:code/display" element={<Navigate to="../play" replace />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
