import { useState, useEffect } from 'react'

// In dev this is empty → relative URLs like "/api/me" (Vite proxies them).
// In production it's the full backend URL (set in Vercel).
const API_URL = import.meta.env.VITE_API_URL || ''

// GitHub logo mark for the login button.
function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

function App() {
  const [user, setUser] = useState(null)
  const [commits, setCommits] = useState([])
  const [leetcode, setLeetcode] = useState(null)
  const [usernameInput, setUsernameInput] = useState('')
  const [tasks, setTasks] = useState([])
  const [stats, setStats] = useState({ streak: 0, history: [] })
  const [loading, setLoading] = useState(true)

  async function loadData() {
    const meRes = await fetch(`${API_URL}/api/me`, { credentials: 'include' })
    if (!meRes.ok) { setUser(null); return }
    setUser(await meRes.json())

    const commitsRes = await fetch(`${API_URL}/api/commits`, { credentials: 'include' })
    setCommits((await commitsRes.json()).commits)

    const lcRes = await fetch(`${API_URL}/api/leetcode`, { credentials: 'include' })
    setLeetcode(await lcRes.json())

    const tasksRes = await fetch(`${API_URL}/api/tasks`, { credentials: 'include' })
    setTasks((await tasksRes.json()).tasks)

    const statsRes = await fetch(`${API_URL}/api/stats`, { credentials: 'include' })
    setStats(await statsRes.json())
  }

  useEffect(() => {
    loadData().finally(() => setLoading(false))
  }, [])

  async function saveUsername(e) {
    e.preventDefault()
    await fetch(`${API_URL}/api/leetcode/username`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username: usernameInput }),
    })
    await loadData()
  }

  async function completeTask(id) {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, completed: true } : t)))
    await fetch(`${API_URL}/api/tasks/${id}/complete`, { method: 'POST', credentials: 'include' })
    const statsRes = await fetch(`${API_URL}/api/stats`, { credentials: 'include' })
    setStats(await statsRes.json())
  }

  if (loading) return <div className="loading">Loading…</div>

  // ---------- logged out: login screen ----------
  if (!user) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <span className="login-badge">1% better every day</span>
          <h1 className="brand">One<span className="pct">Percent</span></h1>
          <p className="tagline">
            Turn your GitHub and LeetCode grind into measurable progress toward
            your next software engineering role.
          </p>
          <ul className="login-features">
            <li><span className="dot" /> Connect GitHub &amp; LeetCode</li>
            <li><span className="dot" /> Turn your activity into points &amp; streaks</li>
            <li><span className="dot" /> Work through a roadmap toward your goal</li>
          </ul>
          <a href={`${API_URL}/auth/login`}>
            <button className="btn-github">
              <GitHubMark /> Continue with GitHub
            </button>
          </a>
          <p className="login-foot">We only read your public activity. Your token is encrypted.</p>
        </div>
      </div>
    )
  }

  // ---------- logged in: dashboard ----------
  const earnedPoints = tasks.filter((t) => t.completed).reduce((s, t) => s + t.points, 0)
  const totalPoints = tasks.reduce((s, t) => s + t.points, 0)
  const progressPct = totalPoints ? Math.round((earnedPoints / totalPoints) * 100) : 0

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="brand-sm">One<span className="pct">Percent</span></div>
        <div className="user-chip">
          {user.avatar_url && <img src={user.avatar_url} alt="" />}
          {user.login}
        </div>
      </header>

      {/* stat cards */}
      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Points</div>
          <div className="stat-value">{earnedPoints}<span className="unit">/ {totalPoints}</span></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Progress to goal</div>
          <div className="stat-value accent">{progressPct}<span className="unit">%</span></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Current streak</div>
          <div className="stat-value">{stats.streak}<span className="unit">day{stats.streak === 1 ? '' : 's'}</span></div>
        </div>
      </div>

      {/* progress bar */}
      <div className="progress-wrap">
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
      </div>

      {/* roadmap */}
      <div className="card section-gap">
        <h2>Your roadmap</h2>
        <ul className="task-list">
          {tasks.map((t) => (
            <li key={t.id} className={`task-row${t.completed ? ' done' : ''}`}>
              <span className="task-title">{t.title}</span>
              <span className="pts-badge">+{t.points}</span>
              {t.completed ? (
                <span className="btn-done">Done</span>
              ) : (
                <button className="btn" onClick={() => completeTask(t.id)}>Complete</button>
              )}
            </li>
          ))}
        </ul>

        {stats.history.length > 0 && (
          <>
            <h3>Points history</h3>
            <ul className="history">
              {stats.history.map((h, i) => (
                <li key={i}>
                  <span className="plus">+{h.points}</span>
                  <span>{h.task_title}</span>
                  <span className="when">{new Date(h.created_at * 1000).toLocaleDateString()}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {/* github + leetcode */}
      <div className="columns">
        <div className="card">
          <h2>Recent commits</h2>
          {commits.length === 0 ? (
            <p className="muted">No recent commits found.</p>
          ) : (
            <ul className="commit-list">
              {commits.map((c) => (
                <li key={c.repo + c.sha} className="commit-item">
                  <div className="commit-top">
                    <span className="sha">{c.sha}</span>
                    <span className="commit-repo">{c.repo}</span>
                  </div>
                  <span className="commit-msg">{c.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h2>LeetCode</h2>
          {leetcode && leetcode.username ? (
            <>
              <p className="lc-user">@{leetcode.username}</p>
              <div className="lc-grid">
                <div className="lc-stat easy"><div className="n">{leetcode.stats?.Easy ?? 0}</div><div className="l">Easy</div></div>
                <div className="lc-stat medium"><div className="n">{leetcode.stats?.Medium ?? 0}</div><div className="l">Medium</div></div>
                <div className="lc-stat hard"><div className="n">{leetcode.stats?.Hard ?? 0}</div><div className="l">Hard</div></div>
                <div className="lc-stat total"><div className="n">{leetcode.stats?.All ?? 0}</div><div className="l">Total</div></div>
              </div>
            </>
          ) : (
            <form className="lc-form" onSubmit={saveUsername}>
              <label>Enter your LeetCode username to track your progress:</label>
              <input
                className="input"
                value={usernameInput}
                onChange={(e) => setUsernameInput(e.target.value)}
                placeholder="e.g. elee136"
              />
              <button type="submit" className="btn-primary">Save username</button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
