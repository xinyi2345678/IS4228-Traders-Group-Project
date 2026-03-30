// =============================================================================
// KPI CARD - Reusable Key Performance Indicator Component
// =============================================================================
// Used across Dashboard and Monitoring pages to display a single metric.
//
// VISUAL LAYOUT:
// +-------------------+
// | LABEL (caption)   |   <- e.g., "Total Portfolio Value"
// | VALUE (h1, mono)  |   <- e.g., "$1,245,300"
// | SUBTEXT (caption)  |   <- e.g., "+4.2% MTD" (colored green/red)
// | [sparkline]       |   <- optional mini trend chart (50x20px)
// +-------------------+
//
// PROPS:
//   - label:         {string}    Metric name displayed as caption
//   - value:         {string}    Formatted metric value (e.g., "$1,245,300")
//   - subtext:       {string}    Additional context below value (e.g., "+4.2% MTD")
//   - subtextColor:  {string}    Tailwind color class for subtext (e.g., "text-profit")
//   - sparklineData: {number[]}  Optional array of ~12 values for mini trend line
// =============================================================================

import { LineChart, Line, ResponsiveContainer } from 'recharts';

export default function KPICard({
  label,
  value,
  subtext,
  secondarySubtext,
  sparklineData,
  subtextColor,
  secondarySubtextColor,
  valueColor,
  sparklineColor,
}) {
  const chartData = sparklineData?.map((v, i) => ({ i, v })) || [];

  return (
    <div className="bg-bg-surface border border-border rounded-lg p-4 flex flex-col gap-1">
      {/* Metric label */}
      <span className="text-text-secondary text-xs uppercase tracking-wide">{label}</span>
      {/* Primary value - displayed in monospace for numeric alignment */}
      <span className={`text-2xl font-semibold font-mono ${valueColor || 'text-text-primary'}`}>{value}</span>
      {/* Subtext - contextual info, color indicates positive/negative */}
      <span className={`text-xs ${subtextColor || 'text-text-secondary'}`}>{subtext}</span>
      {secondarySubtext && (
        <span className={`text-[11px] ${secondarySubtextColor || 'text-text-secondary'}`}>{secondarySubtext}</span>
      )}
      {/* Sparkline - mini trend chart showing recent history */}
      {chartData.length > 0 && (
        <div className="h-8 mt-1">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <Line type="monotone" dataKey="v" stroke={sparklineColor || '#58A6FF'} strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
