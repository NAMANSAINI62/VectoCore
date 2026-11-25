'use client';

import React from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { TrendingUp } from 'lucide-react';
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

export interface CacheHitRateChartProps {
  trends: DailyTrendPoint[];
  overallHitRatePct?: number;
  isLoading?: boolean;
  isError?: boolean;
}

export function CacheHitRateChart({
  trends,
  overallHitRatePct,
  isLoading = false,
  isError = false,
}: CacheHitRateChartProps) {
  const chartData = trends.map((d) => ({
    ...d,
    computedHitRate:
      d.hit_rate_pct !== undefined
        ? d.hit_rate_pct
        : d.requests > 0
          ? Number(((d.hits / d.requests) * 100).toFixed(1))
          : 0,
  }));

  return (
    <ChartContainer
      title="Hit Rate Trend"
      description="Daily cache hit percentage over the selected period"
      icon={<TrendingUp className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={chartData.length === 0}
      emptyTitle="No hit-rate trend data"
      emptyMessage="Hit rate trend lines appear when requests span one or more dates."
      heightClass="h-64"
      badge={
        overallHitRatePct !== undefined ? (
          <span
            className="rounded-full px-2.5 py-1 text-[11px] font-bold tabular-nums"
            style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}
          >
            {overallHitRatePct}% Overall
          </span>
        ) : undefined
      }
      legend={
        <ChartLegend
          items={[
            { label: 'Daily Hit Rate %', color: CHART_COLORS.exactHit },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="date"
            tickFormatter={formatShortDate}
            minTickGap={28}
            tickMargin={8}
            tick={AXIS_TICK_STYLE}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={AXIS_TICK_STYLE}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            content={({ active, payload, label }) => (
              <ChartTooltip
                active={active}
                payload={payload}
                label={label}
                valueFormatter={(val) => `${val.toFixed(1)}%`}
                footerRenderer={(items) => {
                  const row = items[0]?.payload as (DailyTrendPoint & { computedHitRate: number }) | undefined;
                  if (!row) return null;
                  return (
                    <div className="flex items-center justify-between">
                      <span>{row.hits} hits / {row.requests} reqs</span>
                      <span className="font-mono">{row.misses} misses</span>
                    </div>
                  );
                }}
              />
            )}
          />
          <Line
            type="monotone"
            dataKey="computedHitRate"
            name="Hit Rate (%)"
            stroke={CHART_COLORS.exactHit}
            strokeWidth={2.5}
            dot={{ r: 3.5 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
