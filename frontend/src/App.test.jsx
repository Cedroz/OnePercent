import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import App from './App'

// Midnight PT on 2026-09-23 is 07:00:00Z (PDT = UTC-7).
const MIDNIGHT_PT = Date.parse('2026-09-23T07:00:00Z')

// Which day's tasks the fake backend is serving right now.
let serverDay
// Every request the app made, so a test can assert what the rollover triggered.
let calls

function fakeFetch(url, opts = {}) {
  const path = String(url)
  calls.push(`${opts.method || 'GET'} ${path}`)
  const json = (body) => Promise.resolve({ ok: true, json: () => Promise.resolve(body) })

  if (path.endsWith('/api/me')) {
    return json({
      login: 'tester', name: 'Tester', avatar_url: '', big_goal: 'get a job',
      goal_started_at: 1, plan_overview: null, tracked_repo: null,
      plan_updated_at: MIDNIGHT_PT / 1000 - 3600,   // generated yesterday evening
    })
  }
  if (path.endsWith('/api/plan/refresh')) {
    // Mirrors _plan_is_stale(): the server only rebuilds the plan once the Pacific
    // day has actually turned over, so before midnight this is a no-op.
    const stale = Date.now() >= MIDNIGHT_PT
    if (stale) serverDay = 'today'
    return json({ regenerated: stale })
  }
  if (path.endsWith('/api/tasks')) {
    return json({ tasks: [serverDay === 'today'
      ? { id: 3, title: 'TODAY: solve Two Sum', points: 10, completed: false }
      : { id: 1, title: 'YESTERDAY: review big-O', points: 10, completed: false }] })
  }
  if (path.endsWith('/api/stats')) return json({ streak: 0, history: [] })
  if (path.endsWith('/api/commits')) return json({ commits: [] })
  if (path.endsWith('/api/leetcode/recent')) return json({ recent: [] })
  if (path.endsWith('/api/leetcode')) return json({ username: null, stats: {} })
  if (path.endsWith('/api/repos')) return json([])
  return json({})
}

const shows = (text) => document.body.textContent.includes(text)
const countdown = () => (document.body.textContent.match(/\d\d:\d\d:\d\d/) || [null])[0]

// Poll until a condition holds. RTL's waitFor schedules its own timers and stalls
// under a faked clock, so the tests step time forward themselves instead.
async function until(label, cond, ms = 8000) {
  for (let waited = 0; waited < ms; waited += 100) {
    if (cond()) return
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error(`timed out waiting for ${label}; page shows: ${document.body.textContent.slice(0, 300)}`)
}

describe('daily task rollover', () => {
  beforeEach(() => {
    calls = []
    serverDay = 'yesterday'
    vi.stubGlobal('fetch', vi.fn(fakeFetch))
    // Fake clock that still advances with real time, so the component's own 1s
    // interval runs the way it would in a browser.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(MIDNIGHT_PT - 30_000)   // half a minute before midnight PT
  })
  afterEach(() => {
    cleanup()          // globals:false means RTL doesn't auto-unmount between tests
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("replaces yesterday's tasks when the countdown reaches zero", { timeout: 30000 }, async () => {
    render(<App />)

    // Yesterday's plan is on screen, with the countdown in its final seconds.
    await until("yesterday's tasks", () => shows('YESTERDAY: review big-O'))
    expect(countdown()).toMatch(/^00:00:\d\d$/)
    expect(shows('TODAY: solve Two Sum')).toBe(false)

    calls = []   // from here, only what the rollover itself triggers

    // Step to just before midnight; the clock crosses it on its own from there.
    vi.setSystemTime(MIDNIGHT_PT - 300)

    // Nobody reloads the page — it has to pull the new day's plan by itself.
    await until("today's tasks", () => shows('TODAY: solve Two Sum'))

    expect(shows('YESTERDAY: review big-O')).toBe(false)
    expect(calls).toContain('POST /api/plan/refresh')
    expect(calls).toContain('GET /api/tasks')
  })

  it('does not roll over while the countdown is still running', { timeout: 30000 }, async () => {
    vi.setSystemTime(MIDNIGHT_PT - 3600_000)   // an hour still to go
    render(<App />)
    await until("yesterday's tasks", () => shows('YESTERDAY: review big-O'))

    calls = []
    await new Promise((r) => setTimeout(r, 3000))   // several ticks, same Pacific day

    expect(calls).not.toContain('POST /api/plan/refresh')
    expect(shows('YESTERDAY: review big-O')).toBe(true)
    expect(shows('TODAY: solve Two Sum')).toBe(false)
  })
})
