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

export interface RequestVolumeChartProps {
  trends: DailyTrendPoint[];
  isLoading?: boolean;
  isError?: boolean;
}

export function RequestVolumeChart({
  trends,
  isLoading = false,
  isError = false,
}: RequestVolumeChartProps) {
  return (
    <ChartContainer
      title="Request Volume Over Time"
      description="Daily requests separated into Total Requests, Cache Hits and LLM Misses"
      icon={<TrendingUp className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={trends.length === 0}
      emptyTitle="No request volume timeline"
      emptyMessage="Daily requests render once telemetry rows exist."
      heightClass="h-60"
      legend={
        <ChartLegend
          items={[
            { label: 'Total Requests', color: CHART_COLORS.input },
            { label: 'Cache Hits', color: CHART_COLORS.exactHit },
            { label: 'Cache Misses', color: CHART_COLORS.miss },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={trends} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
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
            allowDecimals={false}
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
                valueFormatter={(val) => `${val.toLocaleString()} reqs`}
              />
            )}
          />
          <Line
            type="monotone"
            dataKey="requests"
            name="Total Requests"
            stroke={CHART_COLORS.input}
            strokeWidth={2.5}
            dot={{ r: 3 }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="hits"
            name="Cache Hits"
            stroke={CHART_COLORS.exactHit}
            strokeWidth={2}
            dot={{ r: 3 }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="misses"
            name="Cache Misses"
            stroke={CHART_COLORS.miss}
            strokeWidth={2}
            dot={{ r: 3 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
