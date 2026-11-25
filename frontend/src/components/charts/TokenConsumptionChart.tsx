'use client';

import React, { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Cpu } from 'lucide-react';
import { ModelUsageStat } from '@/store/cacheApi';
import { ChartContainer } from '@/components/charts/ChartContainer';
import {
  AXIS_TICK_STYLE,
  CHART_COLORS,
  formatCompactNumber,
  formatModelShortName,
  GRID_PROPS,
} from '@/components/charts/chartTheme';
import { ChartLegend } from '@/components/analytics/ChartLegend';
import { ChartTooltip } from '@/components/analytics/ChartTooltip';

export interface TokenConsumptionChartProps {
  modelUsage: ModelUsageStat[];
  isLoading?: boolean;
  isError?: boolean;
}

export function TokenConsumptionChart({
  modelUsage,
  isLoading = false,
  isError = false,
}: TokenConsumptionChartProps) {
  const data = useMemo(
    () =>
      modelUsage.map((m) => ({
        ...m,
        shortModel: formatModelShortName(m.model),
      })),
    [modelUsage]
  );

  return (
    <ChartContainer
      title="Input vs Output Token Consumption"
      description="Token volume consumed vs saved across active LLM models"
      icon={<Cpu className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={data.length === 0}
      emptyTitle="No model token usage recorded"
      emptyMessage="Send chat prompts using any configured LLM provider to inspect per-model token footprints."
      heightClass="h-64"
      legend={
        <ChartLegend
          items={[
            { label: 'Input Tokens', color: CHART_COLORS.input },
            { label: 'Output Tokens', color: CHART_COLORS.output },
            { label: 'Tokens Saved', color: CHART_COLORS.exactHit },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="shortModel"
            interval={0}
            angle={-30}
            textAnchor="end"
            height={68}
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
            cursor={{ fill: 'var(--muted)', opacity: 0.35 }}
            content={({ active, payload }) => {
              const row = (payload?.[0]?.payload as (ModelUsageStat & { shortModel: string }) | undefined);
              return (
                <ChartTooltip
                  active={active}
                  payload={payload}
                  label={row ? `${row.provider}/${row.model}` : 'Model'}
                  valueFormatter={(val) => `${val.toLocaleString()} tokens`}
                />
              );
            }}
          />
          <Bar
            dataKey="input_tokens"
            name="Input Tokens"
            fill={CHART_COLORS.input}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
          <Bar
            dataKey="output_tokens"
            name="Output Tokens"
            fill={CHART_COLORS.output}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
          <Bar
            dataKey="tokens_saved"
            name="Tokens Saved"
            fill={CHART_COLORS.exactHit}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
