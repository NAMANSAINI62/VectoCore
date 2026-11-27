'use client';

import React, { memo, useMemo, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { Layers } from 'lucide-react';
import { ChartContainer } from '@/components/charts/ChartContainer';
import { CHART_COLORS, getChartAnimationProps } from '@/components/charts/chartTheme';
import { ChartLegend } from '@/components/analytics/ChartLegend';
import { ChartTooltip } from '@/components/analytics/ChartTooltip';

export interface CacheDistributionChartProps {
  exactHits: number;
  semanticHits: number;
  misses: number;
  blocked?: number;
  fetchCount?: number;
  totalRequests: number;
  hitRatePct?: number;
  isLoading?: boolean;
  isError?: boolean;
}

export const CacheDistributionChart = memo(function CacheDistributionChart({
  exactHits,
  semanticHits,
  misses,
  blocked = 0,
  fetchCount = 0,
  totalRequests,
  hitRatePct,
  isLoading = false,
  isError = false,
}: CacheDistributionChartProps) {
  const [hoveredSlice, setHoveredSlice] = useState<string | null>(null);
  const data = useMemo(
    () =>
      [
        { name: 'Exact Hit', value: exactHits, color: CHART_COLORS.exactHit },
        { name: 'Semantic Hit', value: semanticHits, color: CHART_COLORS.semanticHit },
        { name: 'Cache Miss (LLM)', value: misses, color: CHART_COLORS.miss },
        { name: 'Fetch (MCP)', value: fetchCount, color: '#0284c7' },
        { name: 'Blocked (Guardrails)', value: blocked, color: '#d97706' },
      ].filter((item) => item.value > 0),
    [exactHits, semanticHits, misses, fetchCount, blocked]
  );

  const computedHitRate = useMemo(() => {
    if (hitRatePct !== undefined) return hitRatePct;
    if (totalRequests <= 0) return 0;
    return Number((((exactHits + semanticHits) / totalRequests) * 100).toFixed(1));
  }, [hitRatePct, exactHits, semanticHits, totalRequests]);

  return (
    <ChartContainer
      title="Cache Hit Distribution"
      description="Exact hits vs semantic vector hits vs LLM misses"
      icon={<Layers className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={totalRequests === 0}
      emptyTitle="No requests recorded yet"
      emptyMessage="Send a prompt in the AI Playground to inspect Exact, Semantic, and Miss proportions."
      heightClass="h-64"
      badge={
        <span
          className="rounded-full px-2.5 py-1 text-[11px] font-bold tabular-nums"
          style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}
        >
          {computedHitRate}% Hit Rate
        </span>
      }
      legend={
        <ChartLegend
          items={[
            { label: 'Exact Hit', color: CHART_COLORS.exactHit, value: exactHits },
            { label: 'Semantic Hit', color: CHART_COLORS.semanticHit, value: semanticHits },
            { label: 'Cache Miss', color: CHART_COLORS.miss, value: misses },
            ...(fetchCount > 0 ? [{ label: 'Fetch', color: '#0284c7', value: fetchCount }] : []),
            ...(blocked > 0 ? [{ label: 'Blocked', color: '#d97706', value: blocked }] : []),
          ]}
        />
      }
    >
      <div className="relative h-full w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              startAngle={90}
              endAngle={-270}
              innerRadius="58%"
              outerRadius="82%"
              cornerRadius={data.length > 1 ? 5 : 0}
              paddingAngle={data.length > 1 ? 3 : 0}
              stroke="var(--card)"
              strokeWidth={2}
              onMouseLeave={() => setHoveredSlice(null)}
              {...getChartAnimationProps()}
            >
              {data.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={entry.color}
                  fillOpacity={hoveredSlice && hoveredSlice !== entry.name ? 0.42 : 1}
                  onMouseEnter={() => setHoveredSlice(entry.name)}
                  style={{ transition: 'fill-opacity 180ms ease', cursor: 'pointer' }}
                />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => (
                <ChartTooltip
                  active={active}
                  payload={payload}
                  label="Request Distribution"
                  valueFormatter={(val) => {
                    const pct = totalRequests > 0 ? ((val / totalRequests) * 100).toFixed(1) : '0.0';
                    return `${val.toLocaleString()} (${pct}%)`;
                  }}
                />
              )}
            />
          </PieChart>
        </ResponsiveContainer>

        {/* Center Donut KPI */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            Hit Rate
          </span>
          <span className="text-2xl font-extrabold tabular-nums" style={{ color: 'var(--stat-number)' }}>
            {computedHitRate}%
          </span>
          <span className="text-[11px] font-mono text-[var(--muted-foreground)]">
            {totalRequests.toLocaleString()} reqs
          </span>
        </div>
      </div>
    </ChartContainer>
  );
});
