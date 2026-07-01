import { useState, useEffect } from 'react'

// Read the backend URL from the environment (see .env.local).
// import.meta.env is how Vite exposes VITE_* vars to browser code.
const API_URL = import.meta.env.VITE_API_URL

function App() {
  // useState creates a piece of "state": a value React watches. When you call
  // the setter (setStatus), React re-runs this component and updates the screen.
  // We track two things: the fetched status text, and any error message.
  const [status, setStatus] = useState('loading…')
  const [error, setError] = useState(null)

  // useEffect runs code AFTER the component first renders — the right place for
  // side effects like network calls. The empty array [] at the end means
  // "run this once on mount, never again."
  useEffect(() => {
    fetch(`${API_URL}/health`)              // call the backend
      .then((res) => res.json())            // parse the JSON body
      .then((data) => setStatus(data.status)) // store it in state → screen updates
      .catch((err) => setError(err.message)) // network/CORS failure lands here
  }, [])

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>OnePercent</h1>
      <p>Backend URL: <code>{API_URL}</code></p>
      {error ? (
        <p style={{ color: 'crimson' }}>Error talking to backend: {error}</p>
      ) : (
        <p>Backend health: <strong>{status}</strong></p>
      )}
    </div>
  )
}

export default App
