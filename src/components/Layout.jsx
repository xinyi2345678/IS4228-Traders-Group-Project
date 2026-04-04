// =============================================================================
// LAYOUT COMPONENT - Global Shell
// =============================================================================
// This is the root layout wrapping all pages. It provides:
//   1. SIDEBAR NAVIGATION - icon-only nav linking to the 4 main pages
//   2. TOP BAR - app title, live status indicator, clock
//   3. MAIN CONTENT AREA - where each page renders via <Outlet />
//
// STRUCTURE:
// +--------+-------------------------------------------------+
// | SIDE   | TOP BAR (logo, live status, clock)              |
// | NAV    +-------------------------------------------------+
// | (64px) | MAIN CONTENT AREA (<Outlet /> = current page)   |
// |  [D]   |                                                 |
// |  [P]   |                                                 |
// |  [M]   |                                                 |
// |  [AI]  |                                                 |
// +--------+-------------------------------------------------+
//
// NAVIGATION PAGES:
//   [D]  = Dashboard Overview   (/)            - combined overview of all 4 components
//   [P]  = Portfolio Distribution (/portfolio) - PORTFOLIO OPTIMIZATION component
//   [M]  = Live Monitoring       (/monitoring) - ALGORITHMIC TRADING + REAL-TIME MONITORING
//   [AI] = AI Insights           (/ai-insights)- AI-ASSISTED EXPLANATIONS component
// =============================================================================

import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, PieChart, Activity, Bot } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/portfolio', icon: PieChart, label: 'Portfolio' },
  { to: '/monitoring', icon: Activity, label: 'Monitoring' },
  { to: '/ai-insights', icon: Bot, label: 'AI Insights' },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">

      {/* ================================================================
          SIDEBAR NAVIGATION (64px wide, icon-only)
          - Collapsed by default; hover shows tooltip with page name
          - Active page: blue left accent bar + filled icon
          ================================================================ */}
      <nav className="w-16 bg-bg-surface border-r border-border flex flex-col items-center py-4 gap-2 shrink-0">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `group relative w-12 h-12 flex items-center justify-center rounded-lg transition-colors ${
                isActive
                  ? 'bg-accent/15 text-accent border-l-2 border-accent'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
              }`
            }
          >
            <Icon size={20} />
            {/* Tooltip on hover */}
            <span className="absolute left-14 bg-bg-elevated text-text-primary text-xs px-2 py-1 rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
              {label}
            </span>
          </NavLink>
        ))}
      </nav>

      {/* Main area (top bar + content) */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ================================================================
            TOP BAR (56px height)
            - Left:  App logo/name
            - Right: Live status indicator (green pulsing dot) + current time
            DATA NEEDED:
              - {boolean} isLive - whether the system is connected/running
              - {string}  currentTime - real-time clock (auto-updating)
            ================================================================ */}
        <header className="h-14 bg-bg-surface border-b border-border flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-3">
            <Activity size={20} className="text-accent" />
            <span className="font-semibold text-text-primary text-sm">TradeX: A Regime-Adaptive QTS</span>
          </div>
          <div className="flex items-center gap-4">
            {/* LIVE STATUS INDICATOR
                TODO: Wire to WebSocket connection status
                Shows green pulsing dot when connected, red when disconnected */}
            <span className="flex items-center gap-1.5 text-xs">
              <span className="w-2 h-2 rounded-full bg-profit animate-pulse" />
              <span className="text-profit font-medium">LIVE</span>
            </span>
            {/* CLOCK - auto-updates; currently uses client time */}
            <span className="text-text-secondary text-xs font-mono">
              {new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          </div>
        </header>

        {/* ================================================================
            MAIN CONTENT AREA
            - Scrollable container where each page renders
            - <Outlet /> is replaced by the matched route's component
            ================================================================ */}
        <main className="flex-1 overflow-y-auto p-6 bg-bg-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
