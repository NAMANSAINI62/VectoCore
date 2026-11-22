'use client';

import React from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BarChart3 } from 'lucide-react';
import { DailyTrendPoint } from '@/store/cacheApi';
import { ChartContainer } from '@/components/charts/ChartContainer';
import {
  AXIS_TICK_STYLE,
  CHART_COLORS,
  formatShortDate,
  GRID_PROPS,
} from '@/components/charts/chartTheme';
import { ChartLegend } from '@/components/analytics/ChartLegend';
import { ChartTooltip } from '@/components/analytics/ChartTooltip';

export interface CacheTrendChartProps {
  trends: DailyTrendPoint[];
  isLoading?: boolean;
  isError?: boolean;
}

export function CacheTrendChart({
  trends,
  isLoading = false,
  isError = false,
}: CacheTrendChartProps) {
  return (
    <ChartContainer
      title="Exact vs Semantic vs Miss Trend"
      description="Daily breakdown of Exact hits, Semantic hits, and LLM cache misses"
      icon={<BarChart3 className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={trends.length === 0}
      emptyTitle="No daily trend data"
      emptyMessage="Daily request breakdowns appear once telemetry is logged in this period."
      heightClass="h-64"
      legend={
        <ChartLegend
          items={[
            { label: 'Exact Hit', color: CHART_COLORS.exactHit },
            { label: 'Semantic Hit', color: CHART_COLORS.semanticHit },
            { label: 'Cache Miss (LLM)', color: CHART_COLORS.miss },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={trends} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="date"
            tickFormatter={formatShortDate}
            tick={AXIS_TICK_STYLE}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={AXIS_TICK_STYLE}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: 'var(--muted)', opacity: 0.35 }}
            content={({ active, payload, label }) => (
              <ChartTooltip
                active={active}
                payload={payload}
                label={label}
                footerRenderer={(items) => {
                  const row = items[0]?.payload as DailyTrendPoint | undefined;
                  if (!row) return null;
                  const rate =
                    row.hit_rate_pct !== undefined
                      ? row.hit_rate_pct
                      : row.requests > 0
                        ? Number(((row.hits / row.requests) * 100).toFixed(1))
                        : 0;
                  return (
                    <div className="flex items-center justify-between font-medium">
                      <span>Total: {row.requests} reqs</span>
                      <span className="font-mono">{rate}% hit rate</span>
                    </div>
                  );
                }}
              />
            )}
          />
          <Bar
            dataKey="exact_hits"
            name="Exact Hit"
            stackId="requests"
            fill={CHART_COLORS.exactHit}
            radius={[0, 0, 0, 0]}
            isAnimationActive={false}
          />
          <Bar
            dataKey="semantic_hits"
            name="Semantic Hit"
            stackId="requests"
            fill={CHART_COLORS.semanticHit}
            radius={[0, 0, 0, 0]}
            isAnimationActive={false}
          />
          <Bar
            dataKey="misses"
            name="Cache Miss"
            stackId="requests"
            fill={CHART_COLORS.miss}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
