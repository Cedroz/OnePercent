import { useState, useEffect } from 'react'

// In dev this is empty → relative URLs like "/api/me" (Vite proxies them).
// In production it's the full backend URL (set in Vercel).
const API_URL = import.meta.env.VITE_API_URL || ''

function App() {
  const [user, setUser] = useState(null)          // null = not logged in
  const [commits, setCommits] = useState([])
  const [leetcode, setLeetcode] = useState(null)  // { username, stats } from /api/leetcode
  const [usernameInput, setUsernameInput] = useState('')  // controlled input for the form
  const [loading, setLoading] = useState(true)

  // One async function that loads everything for a logged-in user.
  // (Cleaner than chaining .then()s once there are several calls.)
  async function loadData() {
    const meRes = await fetch(`${API_URL}/api/me`, { credentials: 'include' })
    if (!meRes.ok) {           // 401 → not logged in
      setUser(null)
      return
    }
    setUser(await meRes.json())

    const commitsRes = await fetch(`${API_URL}/api/commits`, { credentials: 'include' })
    setCommits((await commitsRes.json()).commits)

    const lcRes = await fetch(`${API_URL}/api/leetcode`, { credentials: 'include' })
    setLeetcode(await lcRes.json())
  }

  useEffect(() => {
    loadData().finally(() => setLoading(false))
  }, [])

  // Save the LeetCode username, then reload so the stats appear.
  async function saveUsername(e) {
    e.preventDefault()          // stop the form from doing a full-page reload (its default)
    await fetch(`${API_URL}/api/leetcode/username`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username: usernameInput }),
    })
    await loadData()            // refetch → /api/leetcode now returns stats
  }

  if (loading) return <p style={{ padding: '2rem' }}>Loading…</p>

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem', maxWidth: 900, margin: '0 auto' }}>
      <h1>OnePercent</h1>

      {!user ? (
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

          {/* Two columns side by side (flex). Wraps on narrow screens. */}
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
            {/* --- GitHub --- */}
            <div style={{ flex: 1, minWidth: 300 }}>
              <h2>Recent commits</h2>
              {commits.length === 0 ? (
                <p>No recent commits found.</p>
              ) : (
                <ul style={{ lineHeight: 1.7 }}>
                  {commits.map((c) => (
                    <li key={c.repo + c.sha}>
                      <code>{c.sha}</code> — {c.message}{' '}
                      <em style={{ color: '#888' }}>({c.repo})</em>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* --- LeetCode --- */}
            <div style={{ flex: 1, minWidth: 300 }}>
              <h2>LeetCode</h2>
              {leetcode && leetcode.username ? (
                // Username is set → show the counts.
                <div>
                  <p>@{leetcode.username}</p>
                  <ul style={{ lineHeight: 1.7 }}>
                    <li>Easy: <strong>{leetcode.stats?.Easy ?? 0}</strong></li>
                    <li>Medium: <strong>{leetcode.stats?.Medium ?? 0}</strong></li>
                    <li>Hard: <strong>{leetcode.stats?.Hard ?? 0}</strong></li>
                    <li>Total: <strong>{leetcode.stats?.All ?? 0}</strong></li>
                  </ul>
                </div>
              ) : (
                // No username yet → show the input form.
                <form onSubmit={saveUsername}>
                  <p>Enter your LeetCode username:</p>
                  <input
                    value={usernameInput}
                    onChange={(e) => setUsernameInput(e.target.value)}
                    placeholder="username"
                    style={{ padding: '0.4rem', marginRight: 8 }}
                  />
                  <button type="submit" style={{ padding: '0.4rem 0.8rem' }}>Save</button>
                </form>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default App
