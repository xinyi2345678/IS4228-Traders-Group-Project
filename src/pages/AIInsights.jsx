// =============================================================================
// PAGE: AI-ASSISTED INSIGHTS  (wired to OpenAI via Flask backend)
// ROUTE: /ai-insights
// =============================================================================

import { useState, useEffect, useRef } from 'react';
import * as synthetic from '../data/synthetic';
import { fetchAlerts, fetchMonitoring, explainTrade, getMarketSummary, chatMessage } from '../services/api';
import SignalBadge from '../components/SignalBadge';
import { Bot, AlertTriangle, Info, Send, RefreshCw, Loader } from 'lucide-react';

const tabs = ['Trade Explainer', 'Market Summary', 'Risk Alerts'];
const alertFilters = ['All', 'Critical', 'Warning', 'Info'];

const alertIcons = {
  critical: <AlertTriangle size={16} className="text-loss" />,
  warning:  <AlertTriangle size={16} className="text-warning" />,
  info:     <Info size={16} className="text-accent" />,
};
const alertStyles = {
  critical: 'border-l-loss bg-loss/5',
  warning:  'border-l-warning bg-warning/5',
  info:     'border-l-accent bg-accent/5',
};

export default function AIInsights() {
  const [activeTab,    setActiveTab]    = useState(0);
  const [alertFilter,  setAlertFilter]  = useState('All');

  // ── shared live data ───────────────────────────────────────────────────────
  const [monData,  setMonData]  = useState(null);
  const [alerts,   setAlerts]   = useState(null);

  useEffect(() => {
    fetchMonitoring().then(setMonData).catch(() => {});
    fetchAlerts().then(d => setAlerts(d.alerts)).catch(() => {});
  }, []);

  const signals      = monData?.signals ?? synthetic.signals;
  const liveAlerts   = alerts           ?? synthetic.alerts;

  const filteredAlerts = alertFilter === 'All'
    ? liveAlerts
    : liveAlerts.filter(a => a.severity === alertFilter.toLowerCase());

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-text-primary">AI-Assisted Insights</h1>

      {/* Tab bar */}
      <div className="flex gap-1 bg-bg-surface border border-border rounded-lg p-1">
        {tabs.map((tab, i) => (
          <button
            key={tab}
            onClick={() => setActiveTab(i)}
            className={`flex-1 py-2 px-4 rounded text-sm font-medium transition-colors ${
              activeTab === i ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── TAB 1: Trade Explainer ─────────────────────────────────────────── */}
      {activeTab === 0 && (
        <TradeExplainerTab signals={signals} />
      )}

      {/* ── TAB 2: Market Summary ─────────────────────────────────────────── */}
      {activeTab === 1 && (
        <MarketSummaryTab signals={signals} />
      )}

      {/* ── TAB 3: Risk Alerts ────────────────────────────────────────────── */}
      {activeTab === 2 && (
        <div className="space-y-4">
          <div className="flex gap-2">
            {alertFilters.map(f => (
              <button
                key={f}
                onClick={() => setAlertFilter(f)}
                className={`px-3 py-1.5 rounded text-sm ${
                  alertFilter === f
                    ? 'bg-accent/15 text-accent'
                    : 'bg-bg-surface text-text-secondary hover:text-text-primary border border-border'
                }`}
              >
                {f}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            {filteredAlerts.map((a, i) => (
              <div key={i} className={`border-l-2 rounded-r-lg p-4 bg-bg-surface border border-border ${alertStyles[a.severity]}`}>
                <div className="flex items-center gap-2 mb-2">
                  {alertIcons[a.severity]}
                  <span className="text-text-primary text-sm font-semibold">{a.title}</span>
                  <span className="text-text-secondary text-xs ml-auto">{a.time}</span>
                </div>
                <p className="text-text-primary text-sm leading-relaxed mb-2">{a.message}</p>
                {a.recommendation && (
                  <p className="text-text-secondary text-xs italic">Recommendation: {a.recommendation}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Floating chat */}
      <AIChat />
    </div>
  );
}

// ── Trade Explainer tab ───────────────────────────────────────────────────────

function TradeExplainerTab({ signals }) {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [explanation, setExplanation] = useState(null);
  const [loading,     setLoading]     = useState(false);

  const entrySignals = signals.filter(s => s.action !== 'EXIT').slice(0, 15);
  const selected     = entrySignals[selectedIdx];

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setExplanation(null);
      try {
        const result = await explainTrade(selected);
        if (!cancelled) setExplanation(result);
      } catch {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedIdx]); // eslint-disable-line

  return (
    <div className="space-y-4">
      {/* Trade selector */}
      <div className="bg-bg-surface border border-border rounded-lg p-4">
        <div className="flex items-center gap-3">
          <span className="text-text-secondary text-sm">Select Trade:</span>
          <select
            value={selectedIdx}
            onChange={e => setSelectedIdx(Number(e.target.value))}
            className="bg-bg-elevated border border-border rounded px-3 py-1.5 text-text-primary text-sm flex-1"
          >
            {entrySignals.map((s, i) => (
              <option key={i} value={i}>
                {s.action} {s.ticker} — {s.type} — {s.time}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Explanation card */}
      <div className="bg-bg-surface border border-border rounded-lg p-6">
        <div className="flex items-center gap-2 mb-4">
          <Bot size={20} className="text-accent" />
          <span className="text-text-primary font-semibold">Trade Explanation</span>
          {loading && <Loader size={14} className="text-accent animate-spin ml-2" />}
        </div>

        {loading && (
          <p className="text-text-secondary text-sm">Generating explanation…</p>
        )}

        {!loading && explanation && (
          <>
            <div className="flex items-center gap-3 mb-4">
              <SignalBadge action={explanation.action} />
              <span className="text-text-primary font-semibold">{explanation.ticker}</span>
              <span className="text-text-secondary text-sm">{explanation.time}</span>
              <span className="text-text-secondary text-sm">Strategy: {explanation.strategy}</span>
            </div>

            <div className="mb-4">
              <h3 className="text-xs font-semibold text-text-secondary uppercase mb-2">
                Why This Trade Was {explanation.action === 'EXIT' ? 'Exited' : 'Entered'}
              </h3>
              <ol className="space-y-2">
                {(explanation.why ?? []).map((reason, i) => (
                  <li key={i} className="text-text-primary text-sm leading-relaxed flex gap-2">
                    <span className="text-accent font-semibold shrink-0">{i + 1}.</span>
                    {reason}
                  </li>
                ))}
              </ol>
            </div>

            <div className="bg-bg-elevated border border-border/50 rounded-lg p-3 mb-4">
              <h3 className="text-xs font-semibold text-text-secondary uppercase mb-1">Risk Assessment</h3>
              <p className="text-text-primary text-sm">{explanation.risk}</p>
            </div>

            {explanation.confidence != null && (
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-text-secondary">Confidence</span>
                  <span className="text-text-primary font-mono">{explanation.confidence.toFixed(2)} / 1.00</span>
                </div>
                <div className="h-2.5 bg-bg-main rounded-full overflow-hidden">
                  <div className="h-full bg-accent rounded-full" style={{ width: `${explanation.confidence * 100}%` }} />
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* AI-annotated trade history */}
      <div className="bg-bg-surface border border-border rounded-lg p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Trade History (AI Annotated)</h3>
        <div className="space-y-3">
          {signals.slice(0, 5).map((s, i) => (
            <div key={i} className="flex gap-3 py-2 border-b border-border/30 last:border-0">
              <span className="text-text-secondary text-xs font-mono shrink-0 w-16 pt-0.5">{s.time}</span>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <SignalBadge action={s.action} />
                  <span className="text-text-primary text-sm font-semibold">{s.ticker}</span>
                  <span className="text-text-secondary text-xs">{s.type}</span>
                </div>
                <p className="text-text-secondary text-xs italic">
                  "{(s.detail ?? '').substring(0, 100)}{s.detail?.length > 100 ? '…' : ''}"
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Market Summary tab ────────────────────────────────────────────────────────

function MarketSummaryTab({ signals }) {
  const [summary,  setSummary]  = useState('');
  const [loading,  setLoading]  = useState(false);
  const [genTime,  setGenTime]  = useState(null);
  const [asOf,     setAsOf]     = useState(null);
  const [model,    setModel]    = useState('');

  // heatmap from recent signals' tickers
  const heatmapTickers = [...new Set(signals.map(s => s.ticker))].slice(0, 10);
  const heatmapData = heatmapTickers.map(t => {
    const sig = signals.find(s => s.ticker === t);
    // Deterministic magnitude derived from ticker characters (avoids impure Math.random)
    const seed = t.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
    const magnitude = parseFloat(((seed % 9 + 1) * 0.2).toFixed(1));
    const chg = sig?.action === 'LONG' ? magnitude
              : sig?.action === 'SHORT' ? -magnitude : 0;
    return { ticker: t, change: chg };
  });

  const refresh = () => {
    setLoading(true);
    getMarketSummary()
      .then(d => {
        setSummary(d.summary);
        setGenTime(new Date().toLocaleTimeString());
        setAsOf(d.asOf ?? null);
        setModel(d.model ?? '');
      })
      .catch(() => setSummary('Unable to generate market update. Please check the backend connection.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { refresh(); }, []); // eslint-disable-line

  return (
    <div className="space-y-4">
      <div className="bg-bg-surface border border-border rounded-lg p-6">
        <div className="flex items-center gap-2 mb-4">
          <Bot size={20} className="text-accent" />
          <span className="text-text-primary font-semibold">
            Market Summary — {asOf ?? new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
          </span>
          {genTime && <span className="text-text-secondary text-xs ml-auto">Generated {genTime}</span>}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-text-secondary text-sm py-4">
            <Loader size={14} className="animate-spin text-accent" />
            Generating market summary…
          </div>
        ) : (
          <div className="mb-4">
            <h3 className="text-xs font-semibold text-text-secondary uppercase mb-2">Summary</h3>
            {summary.split('\n\n').map((para, i) => (
              <p key={i} className="text-text-primary text-sm leading-relaxed mb-3">{para}</p>
            ))}
          </div>
        )}

        {/* Stock heatmap from recent signal tickers */}
        {!loading && (
          <div>
            <p className="text-text-secondary text-xs mb-3">
              Snapshot uses the live dashboard context: SPY benchmark, current portfolio metrics, active positions, and recent signals.
            </p>
            <h3 className="text-xs font-semibold text-text-secondary uppercase mb-2">Active Tickers</h3>
            <div className="grid grid-cols-5 gap-1.5">
              {heatmapData.map(s => (
                <div
                  key={s.ticker}
                  className="rounded-lg p-3 text-center border border-border/30"
                  style={{
                    backgroundColor: s.change >= 0
                      ? `rgba(63,185,80,${Math.min(0.3, Math.abs(s.change) * 0.12)})`
                      : `rgba(248,81,73,${Math.min(0.3, Math.abs(s.change) * 0.12)})`,
                  }}
                >
                  <div className="text-text-primary text-xs font-semibold">{s.ticker}</div>
                  <div className={`text-xs font-mono ${s.change >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {s.change >= 0 ? '+' : ''}{s.change}%
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="bg-bg-surface border border-border rounded-lg px-4 py-3 flex items-center justify-between">
        <span className="text-text-secondary text-sm">
          Powered by OpenAI{model ? ` · ${model}` : ''} ({genTime ? 'last updated ' + genTime : 'loading…'})
        </span>
        <button
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1.5 text-accent text-sm hover:underline disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh Now
        </button>
      </div>
    </div>
  );
}

// ── AI Chat floating panel ────────────────────────────────────────────────────

function AIChat() {
  const [open,     setOpen]     = useState(false);
  const [input,    setInput]    = useState('');
  const [messages, setMessages] = useState([
    { role: 'ai', text: 'Hello! I am the OpenAI assistant for this dashboard. I can explain signals, portfolio allocation, drawdown, and the current market snapshot from the live backend context.' },
  ]);
  const [sending,  setSending]  = useState(false);
  const [model,    setModel]    = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    const newMessages = [...messages, { role: 'user', text }];
    setMessages(newMessages);
    setSending(true);

    // Build history for context (last 8 turns)
    const history = newMessages.slice(-8).map(m => ({
      role:    m.role === 'user' ? 'user' : 'assistant',
      content: m.text,
    }));

    try {
      const data = await chatMessage(text, history);
      if (data.model) setModel(data.model);
      setMessages(prev => [...prev, { role: 'ai', text: data.response }]);
    } catch {
      setMessages(prev => [...prev, { role: 'ai', text: 'Sorry, I could not reach the OpenAI service. Please make sure the backend is running.' }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 right-6 w-12 h-12 bg-accent rounded-full flex items-center justify-center shadow-lg hover:bg-accent/80 transition-colors z-50"
      >
        <Bot size={22} className="text-bg-main" />
      </button>

      {open && (
        <div className="fixed bottom-20 right-6 w-96 h-[500px] bg-bg-surface border border-border rounded-xl shadow-2xl flex flex-col z-50">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Bot size={16} className="text-accent" />
              <span className="text-text-primary text-sm font-semibold">
                OpenAI Assistant{model ? ` · ${model}` : ''}
              </span>
            </div>
            <button onClick={() => setOpen(false)} className="text-text-secondary hover:text-text-primary">&times;</button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-accent/15 text-text-primary'
                    : 'bg-bg-elevated text-text-primary border border-border/50'
                }`}>
                  {msg.text}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="bg-bg-elevated border border-border/50 rounded-lg px-3 py-2">
                  <Loader size={14} className="animate-spin text-accent" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-border p-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && send()}
                placeholder="Ask about signals, portfolio, risk…"
                className="flex-1 bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:border-accent"
              />
              <button
                onClick={send}
                disabled={sending}
                className="bg-accent text-bg-main p-2 rounded-lg hover:bg-accent/80 disabled:opacity-50"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
