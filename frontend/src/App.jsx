import { useState, useEffect } from 'react'

// In dev this is empty → relative URLs like "/api/me" (Vite proxies them).
// In production it's the full backend URL (set in Vercel).
const API_URL = import.meta.env.VITE_API_URL || ''

// A LeetCode problem link says "solve"; a YouTube tutorial search says "tutorial".
function linkLabel(url) {
  return url && url.includes('leetcode.com/problems') ? 'solve ↗' : 'tutorial ↗'
}

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
  const [recentAc, setRecentAc] = useState([])
  const [usernameInput, setUsernameInput] = useState('')
  const [repos, setRepos] = useState([])
  const [repoInput, setRepoInput] = useState('')
  const [tasks, setTasks] = useState([])
  const [stats, setStats] = useState({ streak: 0, history: [] })
  const [goalInput, setGoalInput] = useState('')
  const [generating, setGenerating] = useState(false)
  const [savingUsername, setSavingUsername] = useState(false)
  const [savingRepo, setSavingRepo] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [showPlan, setShowPlan] = useState(false)
  const [now, setNow] = useState(Date.now())
  const [loading, setLoading] = useState(true)

  async function loadData() {
    const meRes = await fetch(`${API_URL}/api/me`, { credentials: 'include' })
    if (!meRes.ok) { setUser(null); return }
    setUser(await meRes.json())

    const commitsRes = await fetch(`${API_URL}/api/commits`, { credentials: 'include' })
    setCommits((await commitsRes.json()).commits)

    const lcRes = await fetch(`${API_URL}/api/leetcode`, { credentials: 'include' })
    setLeetcode(await lcRes.json())

    const recentRes = await fetch(`${API_URL}/api/leetcode/recent`, { credentials: 'include' })
    setRecentAc((await recentRes.json()).recent)

    const reposRes = await fetch(`${API_URL}/api/repos`, { credentials: 'include' })
    setRepos(await reposRes.json())

    const tasksRes = await fetch(`${API_URL}/api/tasks`, { credentials: 'include' })
    setTasks((await tasksRes.json()).tasks)

    const statsRes = await fetch(`${API_URL}/api/stats`, { credentials: 'include' })
    setStats(await statsRes.json())
  }

  useEffect(() => {
    // Load the dashboard, then auto-sync LeetCode/GitHub activity once so tasks
    // reflect anything solved/committed recently without waiting for the cron.
    loadData()
      .then(() => syncProgress())
      .finally(() => setLoading(false))
  }, [])

  // Run detection for this user, then refresh tasks + stats so any auto-completed
  // tasks show as done and points update.
  async function syncProgress() {
    setSyncing(true)
    try {
      await fetch(`${API_URL}/api/detect`, { method: 'POST', credentials: 'include' })
      const tasksRes = await fetch(`${API_URL}/api/tasks`, { credentials: 'include' })
      setTasks((await tasksRes.json()).tasks)
      const statsRes = await fetch(`${API_URL}/api/stats`, { credentials: 'include' })
      setStats(await statsRes.json())
    } finally {
      setSyncing(false)
    }
  }

  // Tick once a second so the "next refresh" countdown stays live.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)   // cleanup: stop the timer if the component unmounts
  }, [])

  // Format the time left until the plan regenerates (24h after plan_updated_at).
  function countdown() {
    if (!user?.plan_updated_at) return null
    const nextMs = user.plan_updated_at * 1000 + 24 * 60 * 60 * 1000
    let s = Math.floor((nextMs - now) / 1000)
    if (s <= 0) return 'due now'
    const h = String(Math.floor(s / 3600)).padStart(2, '0')
    const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
    s = String(s % 60).padStart(2, '0')
    return `${h}:${m}:${s}`
  }

  async function saveUsername(e) {
    e.preventDefault()
    setSavingUsername(true)
    try {
      await fetch(`${API_URL}/api/leetcode/username`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username: usernameInput }),
      })
      await loadData()
    } finally {
      setSavingUsername(false)
    }
  }

  // Pick the repo to auto-track commits from.
  async function saveRepo(e) {
    e.preventDefault()
    setSavingRepo(true)
    try {
      await fetch(`${API_URL}/api/github/repo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ repo: repoInput }),
      })
      await loadData()
    } finally {
      setSavingRepo(false)
    }
  }

  async function completeTask(id) {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, completed: true } : t)))
    await fetch(`${API_URL}/api/tasks/${id}/complete`, { method: 'POST', credentials: 'include' })
    const statsRes = await fetch(`${API_URL}/api/stats`, { credentials: 'include' })
    setStats(await statsRes.json())
  }

  // Send the goal to the AI planner; it replaces the tasks with a tailored roadmap.
  async function setGoal(e) {
    e.preventDefault()
    setGenerating(true)
    try {
      const res = await fetch(`${API_URL}/api/goal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ goal: goalInput }),
      })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      const data = await res.json()
      setTasks(data.tasks)
      // Stamp plan time locally so the countdown starts right away (the backend
      // just set it to ~now); a later loadData will sync the exact value.
      setUser({ ...user, big_goal: goalInput, plan_updated_at: Date.now() / 1000 })
    } catch (err) {
      // The response may have been lost even though the backend saved the roadmap
      // (slow AI call / serverless timeout). Re-sync from the server so a stuck
      // spinner self-heals into the real state instead of needing a manual refresh.
      console.error('Goal generation failed (re-syncing):', err)
      await loadData()
    } finally {
      setGenerating(false)   // ALWAYS runs, success or failure → spinner can't get stuck
    }
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
  // Progress to goal = points actually earned so far vs. the points that "complete"
  // the goal. Starts at 0 and rises only as you finish tasks; ~500 pts = done, so one
  // full day (~60 pts) ≈ 12% and a bit over a week of daily tasks reaches 100%.
  const GOAL_TARGET_POINTS = 500
  const lifetimeEarned = stats.history.reduce((s, h) => s + h.points, 0)
  const goalProgress = Math.min(100, Math.round((lifetimeEarned / GOAL_TARGET_POINTS) * 100))

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
          <div className="stat-label">Today's points</div>
          <div className="stat-value">{earnedPoints}<span className="unit">/ {totalPoints}</span></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Progress to goal</div>
          <div className="stat-value accent">{goalProgress}<span className="unit">%</span></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Current streak</div>
          <div className="stat-value">{stats.streak}<span className="unit">day{stats.streak === 1 ? '' : 's'}</span></div>
        </div>
      </div>

      {/* progress toward the whole goal (AI estimate) */}
      <div className="progress-wrap">
        <div className="progress-label">
          <span>Progress to goal</span>
          <span>{goalProgress}% · today {earnedPoints}/{totalPoints}</span>
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${goalProgress}%` }} />
        </div>
      </div>

      {/* roadmap */}
      <div className="card section-gap">
        <div className="card-head">
          <h2>Your roadmap</h2>
          {user.big_goal && (
            <button className="btn-change" onClick={syncProgress} disabled={syncing}>
              {syncing ? 'Syncing…' : 'Sync progress'}
            </button>
          )}
        </div>

        {generating ? (
          <div className="generating">
            <span className="spinner" />
            <span className="muted">Generating your roadmap with AI… this takes a few seconds.</span>
          </div>
        ) : !user.big_goal ? (
          // No goal yet → ask for it; the AI builds the roadmap.
          <form className="lc-form" onSubmit={setGoal}>
            <label>What are you working toward? The AI builds your roadmap from it.</label>
            <input
              className="input"
              value={goalInput}
              onChange={(e) => setGoalInput(e.target.value)}
              placeholder="e.g. land an embedded software engineering internship"
            />
            <button type="submit" className="btn-primary">Generate my roadmap</button>
          </form>
        ) : (
          <>
            <p className="goal-line">
              Goal: <strong>{user.big_goal}</strong>
              <button className="btn-change" onClick={() => setUser({ ...user, big_goal: null })}>
                change
              </button>
            </p>

            <div className="plan-bar">
              <span className="muted">
                New tasks in <strong className="mono">{countdown() || '—'}</strong>
              </span>
              <button className="btn-change" onClick={() => setShowPlan((v) => !v)}>
                {showPlan ? 'Hide plan' : 'View plan'}
              </button>
            </div>

            {showPlan && (
              <div className="plan-panel">
                <h3>Today's plan (from Gemini)</h3>
                <ol className="plan-list">
                  {tasks.map((t) => (
                    <li key={t.id}>
                      <div className="plan-main">
                        <span>{t.title}</span>
                        <span className="pts-badge">+{t.points}</span>
                      </div>
                      <div className="plan-meta">
                        {t.metric && <span className="auto-tag">auto-tracked · {t.target} {t.metric}</span>}
                        {t.resource_url && (
                          <a href={t.resource_url} target="_blank" rel="noopener noreferrer">{linkLabel(t.resource_url)}</a>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            <ul className="task-list">
              {tasks.map((t) => (
                <li key={t.id} className={`task-row${t.completed ? ' done' : ''}`}>
                  <span className="task-title">
                    {t.title}
                    {t.resource_url && (
                      <a className="tut-link" href={t.resource_url} target="_blank" rel="noopener noreferrer">
                        {linkLabel(t.resource_url)}
                      </a>
                    )}
                  </span>
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
          </>
        )}
      </div>

      {/* github + leetcode */}
      <div className="columns">
        <div className="card">
          <h2>Recent commits</h2>

          {user.tracked_repo ? (
            <p className="lc-user">
              Tracking <strong>{user.tracked_repo}</strong>
              <button className="btn-change" onClick={() => setUser({ ...user, tracked_repo: null })}>
                change
              </button>
            </p>
          ) : (
            <form className="lc-form" onSubmit={saveRepo}>
              <label>Pick one repo to track commits from:</label>
              <select
                className="input"
                value={repoInput}
                onChange={(e) => setRepoInput(e.target.value)}
              >
                <option value="" disabled>Select a repo…</option>
                {repos.map((r) => (
                  <option key={r.repo} value={r.repo}>{r.repo}</option>
                ))}
              </select>
              <button type="submit" className="btn-primary" disabled={!repoInput || savingRepo}>
                {savingRepo ? (<><span className="spinner spinner-btn" /> Saving…</>) : 'Track this repo'}
              </button>
            </form>
          )}

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

              {recentAc.length > 0 && (
                <>
                  <h3>Recently solved</h3>
                  <ul className="recent-list">
                    {recentAc.map((p) => (
                      <li key={p.slug}>
                        <a href={p.url} target="_blank" rel="noopener noreferrer">{p.title}</a>
                        <span className="when">{new Date(p.timestamp * 1000).toLocaleDateString()}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
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
              <button type="submit" className="btn-primary" disabled={!usernameInput || savingUsername}>
                {savingUsername ? (<><span className="spinner spinner-btn" /> Saving…</>) : 'Save username'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
