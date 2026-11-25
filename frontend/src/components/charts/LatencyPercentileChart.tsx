'use client';

import React, { useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Activity } from 'lucide-react';
import { ChartContainer } from '@/components/charts/ChartContainer';
import {
  AXIS_TICK_STYLE,
  CHART_COLORS,
  formatLatencyMs,
  GRID_PROPS,
} from '@/components/charts/chartTheme';
import { ChartLegend } from '@/components/analytics/ChartLegend';
import { ChartTooltip } from '@/components/analytics/ChartTooltip';

export type LatencyPercentileScope = 'compare' | 'all' | 'hit' | 'miss';

export interface LatencyPercentileChartProps {
  p50All: number;
  p95All: number;
  p99All: number;
  p50Hit: number;
  p95Hit: number;
  p99Hit: number;
  p50Miss: number;
  p95Miss: number;
  p99Miss: number;
  isLoading?: boolean;
  isError?: boolean;
}

export function LatencyPercentileChart({
  p50All,
  p95All,
  p99All,
  p50Hit,
  p95Hit,
  p99Hit,
  p50Miss,
  p95Miss,
  p99Miss,
  isLoading = false,
  isError = false,
}: LatencyPercentileChartProps) {
  const [scope, setScope] = useState<LatencyPercentileScope>('compare');

  const data = useMemo(
    () => [
      { metric: 'P50 (Median)', hit: p50Hit, all: p50All, miss: p50Miss },
      { metric: 'P95', hit: p95Hit, all: p95All, miss: p95Miss },
      { metric: 'P99', hit: p99Hit, all: p99All, miss: p99Miss },
    ],
    [p50All, p95All, p99All, p50Hit, p95Hit, p99Hit, p50Miss, p95Miss, p99Miss]
  );

  const hasData = data.some((d) => d.hit > 0 || d.all > 0 || d.miss > 0);

  return (
    <ChartContainer
      title="Latency Percentiles (P50 / P95 / P99)"
      description="Latency comparison across Hit requests, Miss LLM requests, and All requests"
      icon={<Activity className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={!hasData}
      emptyTitle="No percentile samples yet"
      emptyMessage="Percentiles compute automatically once telemetry requests are logged."
      heightClass="h-64"
      action={
        <div
          role="group"
          aria-label="Latency percentile scope"
          className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--background)]/70 p-0.5 text-[11px]"
        >
          {(
            [
              { id: 'compare', label: 'Compare' },
              { id: 'all', label: 'All' },
              { id: 'hit', label: 'Hit' },
              { id: 'miss', label: 'Miss' },
            ] as const
          ).map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => setScope(opt.id)}
              className={`rounded-md px-2 py-1 font-semibold transition-colors ${
                scope === opt.id
                  ? 'bg-[var(--accent)] text-[var(--accent-foreground)]'
                  : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      }
      legend={
        <ChartLegend
          items={[
            ...(scope === 'compare' || scope === 'hit'
              ? [{ label: 'Cache Hit', color: CHART_COLORS.exactHit }]
              : []),
            ...(scope === 'compare' || scope === 'all'
              ? [{ label: 'All Requests', color: CHART_COLORS.input }]
              : []),
            ...(scope === 'compare' || scope === 'miss'
              ? [{ label: 'Cache Miss', color: CHART_COLORS.miss }]
              : []),
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="metric"
            interval="preserveStartEnd"
            minTickGap={20}
            tickMargin={8}
            tick={AXIS_TICK_STYLE}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
          />
          <YAxis
            tick={AXIS_TICK_STYLE}
            tickFormatter={(v: number) => `${v}ms`}
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
                valueFormatter={(val) => formatLatencyMs(val)}
              />
            )}
          />
          {(scope === 'compare' || scope === 'hit') && (
            <Bar
              dataKey="hit"
              name="Cache Hit"
              fill={CHART_COLORS.exactHit}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          )}
          {(scope === 'compare' || scope === 'all') && (
            <Bar
              dataKey="all"
              name="All Requests"
              fill={CHART_COLORS.input}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          )}
          {(scope === 'compare' || scope === 'miss') && (
            <Bar
              dataKey="miss"
              name="Cache Miss"
              fill={CHART_COLORS.miss}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          )}
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
