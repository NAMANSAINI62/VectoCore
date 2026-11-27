'use client';

import React, { useMemo } from 'react';
import { useGetCacheStatsQuery } from '@/store/cacheApi';
import { useAppSelector } from '@/store';
import { buildDateRangeQueryParams } from '@/store/dateRangeSlice';
import { OverviewHero } from '@/components/dashboard/OverviewHero';
import { DashboardKpiGrid } from '@/components/dashboard/DashboardKpiGrid';
import { QuickNavCards } from '@/components/dashboard/QuickNavCards';
import {
  CacheDistributionChart,
  CacheTrendChart,
  LatencyComparisonChart,
  TokenSavingsChart,
} from '@/components/charts';

export default function OverviewPage() {
  const { selectedDays, appliedCustom } = useAppSelector((state) => state.dateRange);
  const queryParams = useMemo(
    () => buildDateRangeQueryParams(selectedDays, appliedCustom),
    [selectedDays, appliedCustom],
  );
  const { data: stats, isLoading, isError } = useGetCacheStatsQuery(queryParams, {
    pollingInterval: 30000,
    skipPollingIfUnfocused: true,
    refetchOnMountOrArgChange: 15,
  });
  const trends = stats?.daily_trends ?? [];

  return (
    <div className="space-y-6">
      {/* Lightweight Theme-Aware Hero Banner */}
      <OverviewHero stats={stats} isLoading={isLoading} />

      {/* 6 Core KPI Cards */}
      <DashboardKpiGrid stats={stats} isLoading={isLoading} />

      {/* Row 1: Primary Timeline (7 cols) + Hit Distribution Donut (5 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-7">
          <CacheTrendChart trends={trends} isLoading={isLoading} isError={isError} />
        </div>
        <div className="lg:col-span-5">
          <CacheDistributionChart
            exactHits={stats?.exact_hits ?? 0}
            semanticHits={stats?.semantic_hits ?? 0}
            misses={stats?.cache_misses ?? 0}
            blocked={stats?.blocked_requests ?? 0}
            fetchCount={stats?.fetch_requests ?? 0}
            totalRequests={stats?.total_requests ?? 0}
            hitRatePct={stats?.hit_rate_pct}
            isLoading={isLoading}
            isError={isError}
          />
        </div>
      </div>

      {/* Row 2: Latency Comparison + Token Savings Over Time */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <LatencyComparisonChart
          avgExactHitLatencyMs={stats?.avg_exact_hit_latency_ms ?? 0}
          avgSemanticHitLatencyMs={stats?.avg_semantic_hit_latency_ms}
          avgHitLatencyMs={stats?.avg_hit_latency_ms ?? 0}
          avgMissLatencyMs={stats?.avg_miss_latency_ms ?? 0}
          avgOverallLatencyMs={stats?.avg_overall_latency_ms}
          p50LatencyMs={stats?.p50_latency_ms}
          isLoading={isLoading}
          isError={isError}
        />

        <TokenSavingsChart
          trends={trends}
          inputTokensSavedTotal={stats?.input_tokens_saved}
          outputTokensSavedTotal={stats?.output_tokens_saved}
          isLoading={isLoading}
          isError={isError}
        />
      </div>

      {/* Quick Navigation & Tools */}
      <QuickNavCards />
    </div>
  );
}
