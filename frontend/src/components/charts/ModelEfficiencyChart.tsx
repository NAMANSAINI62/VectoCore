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
import { Sparkles } from 'lucide-react';
import { ModelUsageStat } from '@/store/cacheApi';
import { ChartContainer } from '@/components/charts/ChartContainer';
import { AXIS_TICK_STYLE, CHART_COLORS, formatModelShortName, GRID_PROPS } from '@/components/charts/chartTheme';
import { ChartLegend } from '@/components/analytics/ChartLegend';
import { ChartTooltip } from '@/components/analytics/ChartTooltip';

export interface ModelEfficiencyChartProps {
  modelUsage: ModelUsageStat[];
  isLoading?: boolean;
  isError?: boolean;
}

export function ModelEfficiencyChart({
  modelUsage,
  isLoading = false,
  isError = false,
}: ModelEfficiencyChartProps) {
  const data = useMemo(
    () =>
      modelUsage.map((m) => ({
        ...m,
        shortModel: formatModelShortName(m.model),
        hitRatePct: m.requests > 0 ? Number(((m.hits / m.requests) * 100).toFixed(1)) : 0,
      })),
    [modelUsage]
  );

  return (
    <ChartContainer
      title="Model Cache Efficiency"
      description="Cached hits vs LLM misses per model (with hit rate and tokens saved)"
      icon={<Sparkles className="h-4 w-4" />}
      isLoading={isLoading}
      isError={isError}
      isEmpty={data.length === 0}
      emptyTitle="No model efficiency metrics yet"
      emptyMessage="Per-model hit and miss counts appear once requests are recorded."
      heightClass="h-64"
      legend={
        <ChartLegend
          items={[
            { label: 'Cache Hits', color: CHART_COLORS.exactHit },
            { label: 'Cache Misses', color: CHART_COLORS.miss },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="shortModel"
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
            content={({ active, payload }) => {
              const row = payload?.[0]?.payload as (ModelUsageStat & { hitRatePct: number }) | undefined;
              return (
                <ChartTooltip
                  active={active}
                  payload={payload}
                  label={row ? `${row.provider}/${row.model}` : 'Model'}
                  footerRenderer={() =>
                    row ? (
                      <div className="space-y-0.5">
                        <div className="flex items-center justify-between">
                          <span>Hit Rate</span>
                          <span className="font-mono font-semibold">{row.hitRatePct}%</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span>Tokens Saved</span>
                          <span className="font-mono">{row.tokens_saved.toLocaleString()}</span>
                        </div>
                      </div>
                    ) : null
                  }
                />
              );
            }}
          />
          <Bar
            dataKey="hits"
            name="Cache Hits"
            stackId="model"
            fill={CHART_COLORS.exactHit}
            isAnimationActive={false}
          />
          <Bar
            dataKey="misses"
            name="Cache Misses"
            stackId="model"
            fill={CHART_COLORS.miss}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}
