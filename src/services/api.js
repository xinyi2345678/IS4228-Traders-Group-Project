// ── API client for the Flask backend ─────────────────────────────────────────
// All calls use /api/* which Vite proxies to http://localhost:5000

const BASE = '/api';

async function get(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

// ── Endpoints ─────────────────────────────────────────────────────────────────

/** Returns status of the backend data loader: "loading" | "ready" | "error" */
export const fetchStatus     = ()              => get('/status');

/** All data for the Dashboard page */
export const fetchDashboard  = ()              => get('/dashboard');

/** Portfolio allocation, efficient frontier, stock metrics */
export const fetchPortfolio  = ()              => get('/portfolio');

/** Monitoring: positions, signals, KPIs, drawdown, sector exposure */
export const fetchMonitoring = ()              => get('/monitoring');

/** AI-generated risk alerts */
export const fetchAlerts     = ()              => get('/alerts');

/** Ask the OpenAI assistant to explain a specific trading signal */
export const explainTrade    = (signal)        => post('/ai/explain', { signal });

/** Ask the OpenAI assistant for a market summary given current portfolio state */
export const getMarketSummary = ()             => post('/ai/summary', {});

/** Send a chat message to the OpenAI assistant */
export const chatMessage      = (message, history = []) =>
  post('/ai/chat', { message, history });

/** Trigger a fresh data reload on the backend */
export const refreshData      = ()             => post('/refresh', {});
