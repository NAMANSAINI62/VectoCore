'use client';

import React, { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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

export interface LatencyComparisonChartProps {
  avgExactHitLatencyMs: number;
  avgSemanticHitLatencyMs?: number;
  avgHitLatencyMs: number;
  avgMissLatencyMs: number;
  avgOverallLatencyMs?: number;
  p50LatencyMs?: number;
  isLoading?: boolean;
  isError?: boolean;
}

export function LatencyComparisonChart({
  avgExactHitLatencyMs,
  avgSemanticHitLatencyMs,
  avgHitLatencyMs,
  avgMissLatencyMs,
  avgOverallLatencyMs,
  p50LatencyMs,
  isLoading = false,
  isError = false,
}: LatencyComparisonChartProps) {
  const data = useMemo(() => {
    const items = [
      { stage: 'Exact Hit', latencyMs: avgExactHitLatencyMs, color: CHART_COLORS.exactHit },
      {
        stage: avgSemanticHitLatencyMs !== undefined ? 'Semantic Hit' : 'Combined Hit',
        latencyMs: avgSemanticHitLatencyMs ?? avgHitLatencyMs,
        color: CHART_COLORS.semanticHit,
      },
      { stage: 'Cache Miss (LLM)', latencyMs: avgMissLatencyMs, color: CHART_COLORS.miss },
      {
        stage: avgOverallLatencyMs !== undefined ? 'Overall Avg' : 'Overall P50',
        latencyMs: avgOverallLatencyMs ?? p50LatencyMs ?? 0,
        color: CHART_COLORS.input,
      },
    ];
    return items;
  }, [
    avgExactHitLatencyMs,
    avgSemanticHitLatencyMs,
    avgHitLatencyMs,
    avgMissLatencyMs,
    avgOverallLatencyMs,
    p50LatencyMs,
  ]);

  const hasData = data.some((d) => d.latencyMs > 0);
  const speedup =
    avgHitLatencyMs > 0 && avgMissLatencyMs > 0
      ? (avgMissLatencyMs / Math.max(1, avgHitLatencyMs)).toFixed(1)
      : null;

  return (
    <ChartContainer
      title="Latency Comparison"
      description="Average execution latency across Exact Hits, Semantic Hits, LLM Misses, and overall average"
      icon={<Activity className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={!hasData}
      emptyTitle="No latency measurements yet"
      emptyMessage="Complete requests to compare sub-millisecond cache hits against live LLM calls."
      heightClass="h-64"
      badge={
        speedup ? (
          <span
            className="rounded-full px-2.5 py-1 text-[11px] font-bold tabular-nums"
            style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}
          >
            {speedup}x Faster Hits
          </span>
        ) : undefined
      }
      legend={
        <ChartLegend
          items={[
            { label: 'Exact Hit', color: CHART_COLORS.exactHit },
            { label: 'Semantic Hit', color: CHART_COLORS.semanticHit },
            { label: 'Cache Miss', color: CHART_COLORS.miss },
            { label: 'Overall Avg', color: CHART_COLORS.input },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="stage"
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
          <Bar dataKey="latencyMs" name="Latency (ms)" radius={[6, 6, 0, 0]} barSize={44} isAnimationActive={false}>
            {data.map((entry) => (
              <Cell key={entry.stage} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
