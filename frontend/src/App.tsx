import { Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import Library from './pages/Library'
import Book from './pages/Book'
import Render from './pages/Render'
import Job from './pages/Job'
import Voices from './pages/Voices'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Library />} />
        <Route path="/books/:bookId" element={<Book />} />
        <Route path="/books/:bookId/render" element={<Render />} />
        <Route path="/jobs/:jobId" element={<Job />} />
        <Route path="/voices" element={<Voices />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
