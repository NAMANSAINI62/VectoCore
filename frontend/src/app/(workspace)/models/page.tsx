'use client';

import React, { useMemo, useState } from 'react';
import {
  ModelUsageStat,
  useGetCacheStatsQuery,
  useGetModelsQuery,
} from '@/store/cacheApi';
import { useAppSelector } from '@/store';
import { buildDateRangeQueryParams } from '@/store/dateRangeSlice';
import {
  Activity,
  Cpu,
  Link2,
  RefreshCw,
  Search,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import {
  ModelEfficiencyChart,
  TokenConsumptionChart,
} from '@/components/charts';

const RANGE_OPTIONS = [
  { label: 'All time', days: undefined },
  { label: '7D', days: 7 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
];

export default function ModelsPage() {
  const { selectedDays, appliedCustom } = useAppSelector((state) => state.dateRange);
  const [refreshSpin, setRefreshSpin] = useState(false);
  const [providerFilter, setProviderFilter] = useState<string>('all');
  const [search, setSearch] = useState('');

  const {
    data: models = [],
    isLoading: modelsLoading,
    refetch: refetchModels,
  } = useGetModelsQuery(undefined, { refetchOnMountOrArgChange: true });

  const queryParams = useMemo(
    () => buildDateRangeQueryParams(selectedDays, appliedCustom),
    [selectedDays, appliedCustom],
  );

  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
    isFetching,
    refetch,
  } = useGetCacheStatsQuery(queryParams, {
    pollingInterval: 5000,
    refetchOnMountOrArgChange: true,
  });

  const handleRefresh = async () => {
    setRefreshSpin(true);
    await Promise.all([refetch(), refetchModels()]);
    setTimeout(() => setRefreshSpin(false), 450);
  };

  const activeModelKeys = useMemo(
    () => new Set(models.map((m) => `${m.provider}:${m.id}`)),
    [models]
  );

  const activeModelUsage = useMemo(
    () =>
      (stats?.model_usage ?? []).filter((item) =>
        activeModelKeys.has(`${item.provider}:${item.model}`)
      ),
    [stats, activeModelKeys]
  );

  const usageByModel = useMemo(() => {
    const map: Record<string, ModelUsageStat> = {};
    for (const item of activeModelUsage) {
      map[`${item.provider}:${item.model}`] = item;
    }
    return map;
  }, [activeModelUsage]);

  const mergedModels = useMemo(() => {
    return models.map((m) => {
      const usage = usageByModel[`${m.provider}:${m.id}`];
      const requests = usage?.requests ?? 0;
      const hits = usage?.hits ?? 0;
      const hitRate = requests > 0 ? Math.round((hits / requests) * 100) : 0;
      return {
        ...m,
        requests,
        hits,
        misses: usage?.misses ?? 0,
        hitRate,
        input_tokens: usage?.input_tokens ?? 0,
        output_tokens: usage?.output_tokens ?? 0,
        total_tokens: usage?.total_tokens ?? 0,
        tokens_saved: usage?.tokens_saved ?? 0,
        avg_latency_ms: usage?.avg_latency_ms ?? 0,
      };
    });
  }, [models, usageByModel]);

  const activeUsedModels = useMemo(
    () => mergedModels.filter((m) => m.requests > 0),
    [mergedModels]
  );

  const mostUsedModel = useMemo(() => {
    if (!activeUsedModels.length) return '—';
    const sorted = [...activeUsedModels].sort((a, b) => b.requests - a.requests);
    return sorted[0].name;
  }, [activeUsedModels]);

  const totalTokensConsumed =
    (stats?.total_input_tokens ?? 0) + (stats?.total_output_tokens ?? 0);

  const providersList = useMemo(
    () => ['all', ...Array.from(new Set(models.map((m) => m.provider)))],
    [models]
  );

  const filteredModels = useMemo(() => {
    const q = search.trim().toLowerCase();
    return mergedModels.filter((m) => {
      if (providerFilter !== 'all' && m.provider !== providerFilter) return false;
      if (!q) return true;
      return (
        m.name.toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q) ||
        m.provider.toLowerCase().includes(q)
      );
    });
  }, [mergedModels, providerFilter, search]);

  const loading = modelsLoading || statsLoading;

  return (
    <div className="space-y-5">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1
            className="text-2xl font-medium tracking-tight flex items-center gap-2"
            style={{ color: 'var(--foreground)' }}
          >
            <Cpu className="w-5 h-5" style={{ color: 'var(--accent)' }} />
            Model Management
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
            Active provider roster, cache efficiency, latency, and token consumption per model.
          </p>
        </div>
      </div>

      {/* Balanced 4-Column KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div
          className="rounded-xl border p-4 flex flex-col justify-between"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Configured Models
            </span>
            <Cpu className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {loading ? '—' : models.length}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted-foreground)' }}>
            {activeUsedModels.length} with recorded requests
          </div>
        </div>

        <div
          className="rounded-xl border p-4 flex flex-col justify-between"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Total Requests
            </span>
            <Activity className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {loading ? '—' : (stats?.total_requests ?? 0).toLocaleString()}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted-foreground)' }}>
            {stats?.cache_hits ?? 0} hits · {stats?.cache_misses ?? 0} misses
          </div>
        </div>

        <div
          className="rounded-xl border p-4 flex flex-col justify-between"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Most Used Model
            </span>
            <Zap className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          </div>
          <div
            className="text-lg font-medium mt-2 truncate"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
            title={mostUsedModel}
          >
            {loading ? '—' : mostUsedModel}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted-foreground)' }}>
            By total request volume
          </div>
        </div>

        <div
          className="rounded-xl border p-4 flex flex-col justify-between"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Tokens Consumed
            </span>
            <Link2 className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {loading ? '—' : totalTokensConsumed.toLocaleString()}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted-foreground)' }}>
            In: {(stats?.total_input_tokens ?? 0).toLocaleString()} · Out:{' '}
            {(stats?.total_output_tokens ?? 0).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Balanced 2-Column Model Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ModelEfficiencyChart
          modelUsage={activeModelUsage}
          isLoading={statsLoading}
          isError={statsError}
        />
        <TokenConsumptionChart
          modelUsage={activeModelUsage}
          isLoading={statsLoading}
          isError={statsError}
        />
      </div>

      {/* Configured Models Table with Search & Provider Filter */}
      <div className="space-y-3">
        <div
          className="rounded-xl border p-3 flex flex-col md:flex-row md:items-center md:justify-between gap-3"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center gap-3 flex-1">
            <h2
              className="text-sm font-medium flex items-center gap-2 shrink-0"
              style={{ color: 'var(--foreground)' }}
            >
              <Sparkles className="w-4 h-4" style={{ color: 'var(--accent)' }} />
              Configured Models ({filteredModels.length})
            </h2>
            <div className="relative flex-1 max-w-xs">
              <Search
                className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5"
                style={{ color: 'var(--muted-foreground)' }}
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter models..."
                className="w-full pl-8 pr-7 py-1.5 text-xs rounded-lg border focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                style={{
                  backgroundColor: 'var(--background)',
                  borderColor: 'var(--border)',
                  color: 'var(--foreground)',
                }}
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  aria-label="Clear filter"
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-[var(--muted)]"
                  style={{ color: 'var(--muted-foreground)' }}
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          <div
            className="inline-flex flex-wrap items-center gap-1 p-1 rounded-lg border"
            style={{ backgroundColor: 'var(--background)', borderColor: 'var(--border)' }}
          >
            {providersList.map((prov) => (
              <button
                key={prov}
                type="button"
                onClick={() => setProviderFilter(prov)}
                className="px-2.5 py-1 rounded-md text-[11px] font-medium capitalize transition cursor-pointer"
                style={
                  providerFilter === prov
                    ? { backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }
                    : { color: 'var(--muted-foreground)' }
                }
              >
                {prov}
              </button>
            ))}
          </div>
        </div>

        <div
          className="rounded-xl border overflow-hidden"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="custom-scrollbar max-h-[360px] overflow-y-auto overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead
                className="sticky top-0 z-10 text-xs font-medium border-b"
                style={{
                  backgroundColor: 'var(--muted)',
                  color: 'var(--muted-foreground)',
                  borderColor: 'var(--border)',
                }}
              >
                <tr>
                  <th className="px-4 py-2.5">Model</th>
                  <th className="px-3 py-2.5">Provider</th>
                  <th className="px-3 py-2.5 text-right">Requests</th>
                  <th className="px-3 py-2.5 text-right">Hit Rate</th>
                  <th className="px-3 py-2.5 text-right">Tokens (In / Out)</th>
                  <th className="px-3 py-2.5 text-right">Saved</th>
                  <th className="px-4 py-2.5 text-right">Avg Latency</th>
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: 'var(--border)' }}>
                {filteredModels.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-8 text-center text-xs"
                      style={{ color: 'var(--muted-foreground)' }}
                    >
                      No configured models match your current filter.
                    </td>
                  </tr>
                ) : (
                  filteredModels.map((m) => (
                    <tr
                      key={`row-${m.provider}-${m.id}`}
                      className="hover:bg-[var(--muted)]/45 transition-colors"
                    >
                      <td className="px-4 py-2.5 font-semibold" style={{ color: 'var(--foreground)' }}>
                        <div>{m.name}</div>
                        <div
                          className="font-mono text-[10px] font-normal"
                          style={{ color: 'var(--muted-foreground)' }}
                        >
                          {m.id}
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase"
                          style={{ backgroundColor: 'var(--muted)', color: 'var(--foreground)' }}
                        >
                          {m.provider}
                        </span>
                      </td>
                      <td
                        className="px-3 py-2.5 text-right font-semibold tabular-nums"
                        style={{ color: 'var(--stat-number, var(--foreground))' }}
                      >
                        {m.requests}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {m.requests > 0 ? (
                          <span
                            className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold"
                            style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}
                          >
                            {m.hitRate}%
                          </span>
                        ) : (
                          <span style={{ color: 'var(--muted-foreground)' }}>—</span>
                        )}
                      </td>
                      <td
                        className="px-3 py-2.5 text-right font-mono tabular-nums"
                        style={{ color: 'var(--foreground)' }}
                      >
                        {m.input_tokens.toLocaleString()} / {m.output_tokens.toLocaleString()}
                      </td>
                      <td
                        className="px-3 py-2.5 text-right font-semibold tabular-nums"
                        style={{ color: 'var(--hit-text)' }}
                      >
                        {m.tokens_saved.toLocaleString()}
                      </td>
                      <td
                        className="px-4 py-2.5 text-right font-mono tabular-nums"
                        style={{ color: 'var(--foreground)' }}
                      >
                        {m.avg_latency_ms} ms
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
