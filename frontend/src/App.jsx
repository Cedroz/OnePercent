import { useState, useEffect, useRef } from 'react'

// In dev this is empty → relative URLs like "/api/me" (Vite proxies them).
// In production it's the full backend URL (set in Vercel).
const API_URL = import.meta.env.VITE_API_URL || ''

// The Pacific calendar day (YYYY-MM-DD) a timestamp falls on. Plans roll over at
// midnight PT, and the backend decides staleness by this same day boundary.
function pacificDay(ms) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Los_Angeles',
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(ms))
}

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
  const [genError, setGenError] = useState('')
  const [savingUsername, setSavingUsername] = useState(false)
  const [savingRepo, setSavingRepo] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [showPlan, setShowPlan] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [now, setNow] = useState(Date.now())
  const [loading, setLoading] = useState(true)
  const [rollingOver, setRollingOver] = useState(false)
  // The Pacific day the dashboard is currently showing, so the ticking clock can
  // notice when midnight PT passes with the page left open.
  const shownDay = useRef(null)

  async function loadData() {
    const meRes = await fetch(`${API_URL}/api/me`, { credentials: 'include' })
    if (!meRes.ok) { setUser(null); return }
    setUser(await meRes.json())

    // Roll the plan over if a new Pacific day started, before we load the tasks.
    await fetch(`${API_URL}/api/plan/refresh`, { method: 'POST', credentials: 'include' })

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

  // Midnight PT went by while the page sat open. loadData() asks the server to roll
  // the plan over and then reloads, so yesterday's tasks are replaced by today's.
  async function rollOverDay() {
    setRollingOver(true)
    try {
      await loadData()
      await syncProgress()
    } finally {
      setRollingOver(false)
    }
  }

  // Tick once a second so the "next refresh" countdown stays live — and, when the
  // countdown actually reaches zero, pull the new day's tasks instead of leaving
  // yesterday's on screen until someone reloads the page.
  useEffect(() => {
    // Record the starting day up front, not on the first tick — otherwise midnight
    // passing in that first second would arm the check instead of triggering it.
    shownDay.current = pacificDay(Date.now())
    const id = setInterval(() => {
      const ms = Date.now()
      setNow(ms)
      const day = pacificDay(ms)
      if (day !== shownDay.current) {
        shownDay.current = day
        rollOverDay()
      }
    }, 1000)
    return () => clearInterval(id)   // cleanup: stop the timer if the component unmounts
  }, [])

  // Time left until the next midnight US Pacific time, when tasks roll over.
  function countdown() {
    if (!user?.plan_updated_at) return null
    // Read the current wall-clock time in Pacific, then count down to 24:00:00.
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Los_Angeles', hour12: false,
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    }).formatToParts(new Date(now))
    const get = (t) => Number(parts.find((p) => p.type === t).value)
    const secsIntoDay = (get('hour') % 24) * 3600 + get('minute') * 60 + get('second')
    let s = (86400 - secsIntoDay) % 86400
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

  // --- account / settings actions ---
  async function logout() {
    await fetch(`${API_URL}/auth/logout`, { method: 'POST', credentials: 'include' })
    setUser(null)   // back to the login screen
  }

  async function disconnect(path) {
    await fetch(`${API_URL}${path}`, { method: 'POST', credentials: 'include' })
    await loadData()
  }

  async function deleteAccount() {
    if (!window.confirm('Delete your account and all data? This cannot be undone.')) return
    await fetch(`${API_URL}/api/account/delete`, { method: 'POST', credentials: 'include' })
    setUser(null)
  }

  // Send the goal to the AI planner; it replaces the tasks with a tailored roadmap.
  async function setGoal(e) {
    e.preventDefault()
    setGenerating(true)
    setGenError('')
    try {
      const res = await fetch(`${API_URL}/api/goal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ goal: goalInput }),
      })
      if (!res.ok) {
        // Surface the backend's reason (e.g. AI daily limit) instead of failing silently.
        let msg = 'Could not generate your roadmap. Please try again.'
        try { const err = await res.json(); if (err.detail) msg = err.detail } catch {}
        throw new Error(msg)
      }
      const data = await res.json()
      setTasks(data.tasks)
      // Stamp times locally so the countdown + progress reflect the new goal at once.
      setUser({ ...user, big_goal: goalInput, plan_updated_at: Date.now() / 1000, goal_started_at: Date.now() / 1000 })
    } catch (err) {
      // Generation is atomic (nothing saved on failure), so show why and stay on the form.
      console.error('Goal generation failed:', err)
      setGenError(err.message)
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
  // Progress to goal = points earned toward the CURRENT goal (since it was set) vs.
  // the ~500 points that "complete" it. Starts at 0, rises as you finish tasks, and
  // resets when you switch goals (points from the old goal no longer count).
  const GOAL_TARGET_POINTS = 500
  const goalStart = user.goal_started_at || 0
  const earnedTowardGoal = stats.history
    .filter((h) => h.created_at >= goalStart)
    .reduce((s, h) => s + h.points, 0)
  const goalProgress = Math.min(100, Math.round((earnedTowardGoal / GOAL_TARGET_POINTS) * 100))

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="brand-sm">One<span className="pct">Percent</span></div>
        <div className="user-menu">
          <button className="user-chip" onClick={() => setMenuOpen((v) => !v)}>
            {user.avatar_url && <img src={user.avatar_url} alt="" />}
            {user.login}
            <span className="chev" aria-hidden="true">▾</span>
          </button>
          {menuOpen && (
            <>
              <div className="menu-backdrop" onClick={() => setMenuOpen(false)} />
              <div className="menu-dropdown">
                <button onClick={() => { setShowSettings(true); setMenuOpen(false) }}>Settings</button>
                <button onClick={() => { setMenuOpen(false); logout() }}>Log out</button>
              </div>
            </>
          )}
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
            {genError && <p className="form-error">{genError}</p>}
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
              <button
                className="btn-change"
                onClick={() => {
                  if (window.confirm('Changing your goal resets your progress to 0% (points from this goal stop counting). Continue?')) {
                    setUser({ ...user, big_goal: null })
                  }
                }}
              >
                change
              </button>
            </p>

            <div className="plan-bar">
              <span className="muted">
                {rollingOver
                  ? "Generating today's tasks…"
                  : <>New tasks in <strong className="mono">{countdown() || '—'}</strong></>}
              </span>
              <button className="btn-change" onClick={() => setShowPlan((v) => !v)}>
                {showPlan ? 'Hide plan' : 'View plan'}
              </button>
            </div>

            {showPlan && (
              <div className="plan-panel">
                <h3>Your path to this goal</h3>
                {user.plan_overview ? (
                  <>
                    <p className="plan-summary">{user.plan_overview.summary}</p>
                    <ol className="phase-list">
                      {user.plan_overview.phases.map((ph, i) => (
                        <li key={i} className="phase">
                          <div className="phase-head">
                            <span className="phase-title">{ph.title}</span>
                            <span className="phase-dur">{ph.duration}</span>
                          </div>
                          <p className="phase-focus">{ph.focus}</p>
                          <p className="phase-why"><span className="why-label">Why</span> {ph.why}</p>
                        </li>
                      ))}
                    </ol>
                  </>
                ) : (
                  <p className="muted">Set (or re-set) your goal to generate your step-by-step plan.</p>
                )}
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

      {showSettings && (
        <div className="modal-backdrop" onClick={() => setShowSettings(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>Settings</h2>
              <button className="modal-close" onClick={() => setShowSettings(false)} aria-label="Close">×</button>
            </div>

            <section className="settings-section">
              <h3>Account</h3>
              <div className="settings-row">
                <span>Signed in as</span>
                <strong>{user.login}</strong>
              </div>
            </section>

            <section className="settings-section">
              <h3>Connections</h3>
              <div className="settings-row">
                <span>LeetCode</span>
                {leetcode?.username ? (
                  <span className="conn">
                    <strong>@{leetcode.username}</strong>
                    <button className="btn-change" onClick={() => disconnect('/api/leetcode/disconnect')}>Disconnect</button>
                  </span>
                ) : <span className="muted">Not connected</span>}
              </div>
              <div className="settings-row">
                <span>GitHub repo</span>
                {user.tracked_repo ? (
                  <span className="conn">
                    <strong>{user.tracked_repo}</strong>
                    <button className="btn-change" onClick={() => disconnect('/api/github/repo/disconnect')}>Disconnect</button>
                  </span>
                ) : <span className="muted">Not connected</span>}
              </div>
            </section>

            <section className="settings-section danger">
              <h3>Danger zone</h3>
              <div className="settings-row">
                <span>Permanently delete your account and all data.</span>
                <button className="btn-danger" onClick={deleteAccount}>Delete account</button>
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
