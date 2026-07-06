import { useState, useEffect } from 'react'

// In dev this is empty → relative URLs like "/api/me" (Vite proxies them).
// In production it's the full backend URL (set in Vercel).
const API_URL = import.meta.env.VITE_API_URL || ''

function App() {
  const [user, setUser] = useState(null)      // null = not logged in (or not checked yet)
  const [commits, setCommits] = useState([])
  const [loading, setLoading] = useState(true)

  // On first load, ask the backend "who am I?". The session cookie is sent
  // because of `credentials: 'include'` (without it, the browser omits cookies
  // on cross-origin requests). 200 → logged in; 401 → show the login button.
  useEffect(() => {
    fetch(`${API_URL}/api/me`, { credentials: 'include' })
      .then((res) => {
        if (!res.ok) throw new Error('not logged in')  // turns 401 into a caught error
        return res.json()
      })
      .then((me) => {
        setUser(me)
        // Logged in — now go fetch the commits.
        return fetch(`${API_URL}/api/commits`, { credentials: 'include' })
      })
      .then((res) => res.json())
      .then((data) => setCommits(data.commits))
      .catch(() => setUser(null))     // not logged in — perfectly fine, show login
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p style={{ padding: '2rem' }}>Loading…</p>

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem', maxWidth: 720, margin: '0 auto' }}>
      <h1>OnePercent</h1>

      {!user ? (
        // A plain link (full-page navigation), NOT a fetch — OAuth needs the
        // browser to actually travel to GitHub and back, setting cookies en route.
        <a href={`${API_URL}/auth/login`}>
          <button style={{ padding: '0.6rem 1rem', fontSize: '1rem' }}>
            Login with GitHub
          </button>
        </a>
      ) : (
        <>
          <p>
            {user.avatar_url && (
              <img
                src={user.avatar_url}
                width="32"
                height="32"
                style={{ borderRadius: '50%', verticalAlign: 'middle', marginRight: 8 }}
              />
            )}
            Logged in as <strong>{user.login}</strong>
          </p>

          <h2>Recent commits</h2>
          {commits.length === 0 ? (
            <p>No recent commits found.</p>
          ) : (
            <ul style={{ lineHeight: 1.7 }}>
              {/* .map() turns each commit object into an <li>. React needs a
                  unique `key` per item to track them efficiently. */}
              {commits.map((c) => (
                <li key={c.repo + c.sha}>
                  <code>{c.sha}</code> — {c.message}{' '}
                  <em style={{ color: '#888' }}>({c.repo})</em>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

export default App
