'use client';

import React, { useMemo, useState } from 'react';
import {
  useGetCacheStatsQuery,
  useGetModelsQuery,
  TelemetryItem,
} from '@/store/cacheApi';
import { useAppSelector } from '@/store';
import { buildDateRangeQueryParams } from '@/store/dateRangeSlice';
import {
  CacheHitRateChart,
  CacheTrendChart,
  LatencyPercentileChart,
  ModelEfficiencyChart,
  TokenConsumptionChart,
  TokenSavingsChart,
} from '@/components/charts';
import { getBadgeLabel, getBadgeStyle } from '@/components/logs/TelemetryTraceModal';
import {
  Activity,
  BarChart3,
  Cpu,
  Database,
  Gauge,
  Layers,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { getLanguageLabel } from '@/lib/languages';

type AnalyticsTab = 'overview' | 'models' | 'activity' | 'all';

function formatCompact(n: number): string {
  return n.toLocaleString();
}

export default function AnalyticsPage() {
  const { selectedDays, appliedCustom } = useAppSelector((state) => state.dateRange);
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('overview');

  const queryParams = useMemo(
    () => buildDateRangeQueryParams(selectedDays, appliedCustom),
    [selectedDays, appliedCustom],
  );

  const {
    data: stats,
    isLoading,
    isError,
  } = useGetCacheStatsQuery(queryParams, {
    pollingInterval: 30000,
    skipPollingIfUnfocused: true,
    refetchOnMountOrArgChange: 15,
  });

  const { data: activeModels = [] } = useGetModelsQuery();

  const filteredModelUsage = useMemo(() => {
    const raw = stats?.model_usage ?? [];
    if (activeModels.length === 0) return raw;
    const activeKeys = new Set(activeModels.map((m) => `${m.provider}:${m.id}`));
    return raw.filter((m) => activeKeys.has(`${m.provider}:${m.model}`));
  }, [stats?.model_usage, activeModels]);

  const recentActivity: TelemetryItem[] = stats?.recent_activity ?? [];
  const trends = stats?.daily_trends ?? [];

  const tabs: Array<{ id: AnalyticsTab; label: string; icon: React.ReactNode }> = [
    { id: 'overview', label: 'Overview & Trends', icon: <BarChart3 className="w-3.5 h-3.5" /> },
    { id: 'models', label: 'Models & Tokens', icon: <Cpu className="w-3.5 h-3.5" /> },
    { id: 'activity', label: 'Recent Activity', icon: <Database className="w-3.5 h-3.5" /> },
    { id: 'all', label: 'All Charts', icon: <Layers className="w-3.5 h-3.5" /> },
  ];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div>
          <h1
            className="text-2xl font-medium tracking-tight flex items-center gap-2"
            style={{ color: 'var(--foreground)' }}
          >
            <Activity className="w-5 h-5" style={{ color: 'var(--accent)' }} />
            Analytics &amp; Cache Performance
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
            Real-time cache efficiency, latency percentiles, token savings, and active model telemetry.
          </p>
        </div>
      </div>

      {/* 4-Column Balanced KPI Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* KPI 1: Real Tokens Saved */}
        <div
          className="rounded-xl border p-4 flex flex-col justify-between transition-colors"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Real Tokens Saved
            </span>
            <span
              className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
            >
              <Zap className="w-3.5 h-3.5" />
            </span>
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {isLoading ? '—' : formatCompact(stats?.real_tokens_saved ?? 0)}
          </div>
          <div className="text-[11px] mt-1.5" style={{ color: 'var(--muted-foreground)' }}>
            In: {formatCompact(stats?.input_tokens_saved ?? 0)} · Out:{' '}
            {formatCompact(stats?.output_tokens_saved ?? 0)}
          </div>
        </div>

        {/* KPI 2: Cache Hit Rate */}
        <div
          className="rounded-xl border p-4 flex flex-col justify-between transition-colors"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Cache Hit Rate
            </span>
            <span
              className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}
            >
              <Database className="w-3.5 h-3.5" />
            </span>
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {isLoading ? '—' : `${(stats?.hit_rate_pct ?? 0).toFixed(1)}%`}
          </div>
          <div className="text-[11px] mt-1.5" style={{ color: 'var(--muted-foreground)' }}>
            {stats?.exact_hits ?? 0} exact · {stats?.semantic_hits ?? 0} semantic ·{' '}
            {stats?.cache_misses ?? 0} misses
          </div>
        </div>

        {/* KPI 3: Avg Hit Latency */}
        <div
          className="rounded-xl border p-4 flex flex-col justify-between transition-colors"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Avg Hit Latency
            </span>
            <span
              className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
            >
              <Gauge className="w-3.5 h-3.5" />
            </span>
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {isLoading ? '—' : `${Math.round(stats?.avg_hit_latency_ms ?? 0)}ms`}
          </div>
          <div className="text-[11px] mt-1.5" style={{ color: 'var(--muted-foreground)' }}>
            Exact: {Math.round(stats?.avg_exact_hit_latency_ms ?? 0)}ms · Miss:{' '}
            {Math.round(stats?.avg_miss_latency_ms ?? 0)}ms
          </div>
        </div>

        {/* KPI 4: LLM Calls Avoided */}
        <div
          className="rounded-xl border p-4 flex flex-col justify-between transition-colors"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              LLM Calls Avoided
            </span>
            <span
              className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
            </span>
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {isLoading ? '—' : formatCompact(stats?.llm_calls_avoided ?? stats?.cache_hits ?? 0)}
          </div>
          <div className="text-[11px] mt-1.5" style={{ color: 'var(--muted-foreground)' }}>
            {formatCompact(stats?.total_requests ?? 0)} requests ·{' '}
            {formatCompact(stats?.total_entries_count ?? 0)} cached
          </div>
        </div>
      </div>

      {/* Segmented View Tabs */}
      <div
        className="inline-flex flex-wrap items-center gap-1 p-1 rounded-xl border"
        style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
      >
        {tabs.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
              style={
                active
                  ? { backgroundColor: 'var(--accent)', color: '#ffffff' }
                  : { color: 'var(--muted-foreground)' }
              }
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Overview & Trends */}
      {(activeTab === 'overview' || activeTab === 'all') && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <CacheHitRateChart
              trends={trends}
              overallHitRatePct={stats?.hit_rate_pct}
              isLoading={isLoading}
              isError={isError}
            />
            <CacheTrendChart
              trends={trends}
              isLoading={isLoading}
              isError={isError}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <LatencyPercentileChart
              p50All={stats?.p50_latency_ms ?? 0}
              p95All={stats?.p95_latency_ms ?? 0}
              p99All={stats?.p99_latency_ms ?? 0}
              p50Hit={stats?.p50_hit_latency_ms ?? 0}
              p95Hit={stats?.p95_hit_latency_ms ?? 0}
              p99Hit={stats?.p99_hit_latency_ms ?? 0}
              p50Miss={stats?.p50_miss_latency_ms ?? 0}
              p95Miss={stats?.p95_miss_latency_ms ?? 0}
              p99Miss={stats?.p99_miss_latency_ms ?? 0}
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
        </div>
      )}

      {/* Models & Tokens (Balanced 2-column grid, filtered to active models) */}
      {(activeTab === 'models' || activeTab === 'all') && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TokenConsumptionChart
            modelUsage={filteredModelUsage}
            isLoading={isLoading}
            isError={isError}
          />
          <ModelEfficiencyChart
            modelUsage={filteredModelUsage}
            isLoading={isLoading}
            isError={isError}
          />
        </div>
      )}

      {/* Recent Activity */}
      {(activeTab === 'activity' || activeTab === 'all') && (
        <div
          className="rounded-xl border p-4"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between gap-2 mb-3">
            <div>
              <h2
                className="text-sm font-semibold flex items-center gap-2"
                style={{ color: 'var(--foreground)' }}
              >
                <Database className="w-4 h-4" style={{ color: 'var(--accent)' }} />
                Cache Telemetry &amp; Activity
              </h2>
              <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
                Latest {recentActivity.length} cache execution records ordered newest first
              </p>
            </div>
            <span
              className="text-[11px] font-medium px-2.5 py-1 rounded-full border"
              style={{
                borderColor: 'var(--border)',
                color: 'var(--muted-foreground)',
                backgroundColor: 'var(--background)',
              }}
            >
              Showing {recentActivity.length} recent
            </span>
          </div>

          {recentActivity.length === 0 ? (
            <div
              className="py-8 text-center text-xs rounded-lg border border-dashed"
              style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
            >
              {isLoading ? 'Loading recent cache telemetry...' : 'No telemetry records in this period.'}
            </div>
          ) : (
            <div className="custom-scrollbar max-h-[380px] overflow-y-auto space-y-2 pr-1">
              {recentActivity.map((item) => {
                const badgeLabel = getBadgeLabel(item.cache_status);
                const badgeStyle = getBadgeStyle(item.cache_status);
                const isHit =
                  item.cache_status === 'exact_hit' || item.cache_status === 'semantic_hit';
                const timestamp = item.created_at
                  ? new Date(item.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })
                  : '';

                const reqKey = item.request_id ?? item.id;
                return (
                  <div
                    key={reqKey}
                    className="rounded-lg border px-3 py-2.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"
                    style={{
                      backgroundColor: 'var(--background)',
                      borderColor: 'var(--border)',
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className="text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide shrink-0"
                          style={badgeStyle}
                        >
                          {badgeLabel}
                        </span>
                        <span
                          className="text-[11px] font-mono shrink-0"
                          style={{ color: 'var(--muted-foreground)' }}
                        >
                          req: {reqKey.slice(0, 8)}
                        </span>
                        <span
                          className="text-xs font-medium truncate"
                          style={{ color: 'var(--foreground)' }}
                          title={item.query_preview}
                        >
                          {item.query_preview}
                        </span>
                      </div>
                      <div
                        className="text-[11px] mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5"
                        style={{ color: 'var(--muted-foreground)' }}
                      >
                        <span>Lang: {getLanguageLabel(item.detected_language || 'en')}</span>
                        <span>Model: {item.model}</span>
                        <span>
                          Tokens: {item.input_tokens} in · {item.output_tokens} out
                        </span>
                        {timestamp && <span>{timestamp}</span>}
                      </div>
                    </div>

                    <div className="text-left sm:text-right shrink-0">
                      <div
                        className="text-xs font-medium tabular-nums"
                        style={{ color: 'var(--foreground)' }}
                      >
                        {isHit ? `Cache: ${item.cache_lookup_latency_ms}ms · ` : ''}
                        Total: {item.total_latency_ms}ms
                      </div>
                      <div
                        className="text-[11px] tabular-nums"
                        style={{
                          color: item.tokens_saved > 0 ? 'var(--hit-text)' : 'var(--muted-foreground)',
                        }}
                      >
                        +{formatCompact(item.tokens_saved)} tokens saved
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
