import { Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import Library from './pages/Library'
import Voices from './pages/Voices'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Library />} />
        <Route path="/voices" element={<Voices />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
