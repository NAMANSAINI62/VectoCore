'use client';

import React from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Zap } from 'lucide-react';
import { DailyTrendPoint } from '@/store/cacheApi';
import { ChartContainer } from '@/components/charts/ChartContainer';
import {
  AXIS_TICK_STYLE,
  CHART_COLORS,
  formatCompactNumber,
  formatShortDate,
  GRID_PROPS,
} from '@/components/charts/chartTheme';
import { ChartLegend } from '@/components/analytics/ChartLegend';
import { ChartTooltip } from '@/components/analytics/ChartTooltip';

export interface TokenSavingsChartProps {
  trends: DailyTrendPoint[];
  inputTokensSavedTotal?: number;
  outputTokensSavedTotal?: number;
  isLoading?: boolean;
  isError?: boolean;
}

export function TokenSavingsChart({
  trends,
  inputTokensSavedTotal,
  outputTokensSavedTotal,
  isLoading = false,
  isError = false,
}: TokenSavingsChartProps) {
  return (
    <ChartContainer
      title="Token Savings Over Time"
      description="Daily Input and Output tokens avoided using Exact and Semantic cache hits"
      icon={<Zap className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={trends.length === 0}
      emptyTitle="No token savings history"
      emptyMessage="Token savings trends appear once cached hits are recorded."
      heightClass="h-64"
      legend={
        <ChartLegend
          items={[
            {
              label: 'Input Saved',
              color: CHART_COLORS.input,
              value:
                inputTokensSavedTotal !== undefined ? inputTokensSavedTotal.toLocaleString() : undefined,
            },
            {
              label: 'Output Saved',
              color: CHART_COLORS.output,
              value:
                outputTokensSavedTotal !== undefined ? outputTokensSavedTotal.toLocaleString() : undefined,
            },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={trends} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
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
            tick={AXIS_TICK_STYLE}
            tickFormatter={formatCompactNumber}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            content={({ active, payload, label }) => (
              <ChartTooltip
                active={active}
                payload={payload}
                label={label}
                valueFormatter={(val) => `${val.toLocaleString()} tokens`}
                footerRenderer={(items) => {
                  const row = items[0]?.payload as DailyTrendPoint | undefined;
                  if (!row) return null;
                  return (
                    <div className="flex items-center justify-between font-medium">
                      <span>Total Saved</span>
                      <span className="font-mono">{row.tokens_saved.toLocaleString()} tokens</span>
                    </div>
                  );
                }}
              />
            )}
          />
          <Area
            type="monotone"
            dataKey="input_tokens_saved"
            name="Input Tokens Saved"
            stackId="tokens"
            stroke={CHART_COLORS.input}
            fill={CHART_COLORS.input}
            fillOpacity={0.35}
            strokeWidth={2}
            dot={{ r: 2.5 }}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="output_tokens_saved"
            name="Output Tokens Saved"
            stackId="tokens"
            stroke={CHART_COLORS.output}
            fill={CHART_COLORS.output}
            fillOpacity={0.35}
            strokeWidth={2}
            dot={{ r: 2.5 }}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
