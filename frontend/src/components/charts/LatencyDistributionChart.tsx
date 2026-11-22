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
import { Activity } from 'lucide-react';
import { LatencyBucketStat } from '@/store/cacheApi';
import { ChartContainer } from '@/components/charts/ChartContainer';
import { AXIS_TICK_STYLE, CHART_COLORS, GRID_PROPS } from '@/components/charts/chartTheme';
import { ChartLegend } from '@/components/analytics/ChartLegend';
import { ChartTooltip } from '@/components/analytics/ChartTooltip';

export interface LatencyDistributionChartProps {
  buckets: LatencyBucketStat[];
  isLoading?: boolean;
  isError?: boolean;
}

export function LatencyDistributionChart({
  buckets,
  isLoading = false,
  isError = false,
}: LatencyDistributionChartProps) {
  const totalCount = buckets.reduce((acc, b) => acc + b.count, 0);

  return (
    <ChartContainer
      title="Request Latency Histogram"
      description="Individual request counts across millisecond latency"
      icon={<Activity className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={totalCount === 0}
      emptyTitle="No latency samples yet"
      emptyMessage="Individual request latency counts appear once telemetry requests are logged."
      heightClass="h-60"
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
        <BarChart data={buckets} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="bucket"
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
                label={`Latency Bucket: ${label}`}
                valueFormatter={(val) => `${val.toLocaleString()} reqs`}
                footerRenderer={(items) => {
                  const row = items[0]?.payload as LatencyBucketStat | undefined;
                  if (!row) return null;
                  return (
                    <div className="flex items-center justify-between font-medium">
                      <span>Bucket Total</span>
                      <span className="font-mono">{row.count} reqs</span>
                    </div>
                  );
                }}
              />
            )}
          />
          <Bar
            dataKey="exact_hits"
            name="Exact Hit"
            stackId="lat"
            fill={CHART_COLORS.exactHit}
            isAnimationActive={false}
          />
          <Bar
            dataKey="semantic_hits"
            name="Semantic Hit"
            stackId="lat"
            fill={CHART_COLORS.semanticHit}
            isAnimationActive={false}
          />
          <Bar
            dataKey="misses"
            name="Cache Miss"
            stackId="lat"
            fill={CHART_COLORS.miss}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
