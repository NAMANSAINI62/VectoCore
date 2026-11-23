'use client';

import React, { useMemo, useState } from 'react';
import {
  TelemetryItem,
  useGetCacheStatsQuery,
  useInspectTelemetryItemQuery,
} from '@/store/cacheApi';
import {
  Activity,
  BarChart3,
  Clock,
  RefreshCw,
  ScrollText,
  Search,
  X,
  Zap,
} from 'lucide-react';
import {
  LatencyDistributionChart,
  RequestVolumeChart,
} from '@/components/charts';
import {
  TelemetryTraceModal,
  getBadgeLabel,
  getBadgeStyle,
} from '@/components/logs/TelemetryTraceModal';

const STATUS_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'exact_hit', label: 'Exact Hit' },
  { id: 'semantic_hit', label: 'Semantic Hit' },
  { id: 'miss', label: 'Miss' },
  { id: 'bypass', label: 'Bypass' },
  { id: 'blocked', label: 'Blocked' },
  { id: 'error', label: 'Error' },
] as const;

type StatusFilter = (typeof STATUS_FILTERS)[number]['id'];

export default function LogsPage() {
  const { data: stats, isLoading, isError, isFetching, refetch } = useGetCacheStatsQuery(
    { activity_limit: 500 },
    { pollingInterval: 5000, refetchOnMountOrArgChange: true }
  );
  const [refreshSpin, setRefreshSpin] = useState(false);
  const [showCharts, setShowCharts] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [selectedLog, setSelectedLog] = useState<TelemetryItem | null>(null);

  const { data: inspectedLog, isFetching: inspecting } = useInspectTelemetryItemQuery(
    selectedLog?.id ?? '',
    { skip: !selectedLog?.id }
  );
  const activeLog = selectedLog
    ? inspectedLog && inspectedLog.id === selectedLog.id
      ? inspectedLog
      : selectedLog
    : null;

  const rawActivity = useMemo(
    () => stats?.recent_activity ?? [],
    [stats?.recent_activity]
  );

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: rawActivity.length };
    for (const item of rawActivity) {
      counts[item.cache_status] = (counts[item.cache_status] ?? 0) + 1;
    }
    return counts;
  }, [rawActivity]);

  const logs = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rawActivity.filter((item) => {
      if (statusFilter !== 'all' && item.cache_status !== statusFilter) return false;
      if (!q) return true;
      const reqId = (item.request_id || `req-${item.id.slice(0, 8)}`).toLowerCase();
      return (
        item.query_preview.toLowerCase().includes(q) ||
        reqId.includes(q) ||
        item.id.toLowerCase().includes(q) ||
        (item.matched_query ?? '').toLowerCase().includes(q) ||
        item.model.toLowerCase().includes(q)
      );
    });
  }, [rawActivity, search, statusFilter]);

  const summary = useMemo(() => {
    const total = logs.length;
    const hits = logs.filter(
      (i) => i.cache_status === 'exact_hit' || i.cache_status === 'semantic_hit'
    ).length;
    const misses = logs.filter((i) => i.cache_status === 'miss').length;
    const avgLatency =
      total > 0
        ? Math.round(logs.reduce((acc, i) => acc + (i.total_latency_ms ?? 0), 0) / total)
        : 0;
    return { total, hits, misses, avgLatency };
  }, [logs]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1
            className="text-2xl font-medium tracking-tight flex items-center gap-2"
            style={{ color: 'var(--foreground)' }}
          >
            <ScrollText className="w-5 h-5" style={{ color: 'var(--accent)' }} />
            Request Logs &amp; Execution History
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
            Inspect individual request traces, cache lookup vs LLM latency, and token accounting.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowCharts((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition cursor-pointer"
            style={{
              backgroundColor: 'var(--card)',
              borderColor: 'var(--border)',
              color: 'var(--foreground)',
            }}
          >
            <BarChart3 className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
            {showCharts ? 'Hide Charts' : 'Show Charts'}
          </button>
        </div>
      </div>

      {/* 4-Column Summary Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div
          className="rounded-xl border p-3.5"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between text-xs font-medium" style={{ color: 'var(--muted-foreground)' }}>
            <span>Matching Logs</span>
            <ScrollText className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
          </div>
          <div className="text-2xl font-medium tracking-tight mt-1.5 tabular-nums" style={{ color: 'var(--stat-number, var(--foreground))' }}>
            {isLoading ? '—' : summary.total}
          </div>
        </div>

        <div
          className="rounded-xl border p-3.5"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between text-xs font-medium" style={{ color: 'var(--muted-foreground)' }}>
            <span>Cache Hits</span>
            <Zap className="w-3.5 h-3.5" style={{ color: 'var(--hit-text)' }} />
          </div>
          <div className="text-2xl font-medium tracking-tight mt-1.5 tabular-nums" style={{ color: 'var(--hit-text)' }}>
            {isLoading ? '—' : summary.hits}
          </div>
        </div>

        <div
          className="rounded-xl border p-3.5"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between text-xs font-medium" style={{ color: 'var(--muted-foreground)' }}>
            <span>LLM Misses</span>
            <Activity className="w-3.5 h-3.5" style={{ color: 'var(--miss-text)' }} />
          </div>
          <div className="text-2xl font-medium tracking-tight mt-1.5 tabular-nums" style={{ color: 'var(--miss-text)' }}>
            {isLoading ? '—' : summary.misses}
          </div>
        </div>

        <div
          className="rounded-xl border p-3.5"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between text-xs font-medium" style={{ color: 'var(--muted-foreground)' }}>
            <span>Avg Latency</span>
            <Clock className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
          </div>
          <div className="text-2xl font-medium tracking-tight mt-1.5 tabular-nums" style={{ color: 'var(--stat-number, var(--foreground))' }}>
            {isLoading ? '—' : `${summary.avgLatency}ms`}
          </div>
        </div>
      </div>

      {/* Collapsible Charts */}
      {showCharts && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <RequestVolumeChart trends={stats?.daily_trends ?? []} isLoading={isLoading} isError={isError} />
          <LatencyDistributionChart buckets={stats?.latency_buckets ?? []} isLoading={isLoading} isError={isError} />
        </div>
      )}

      {/* Search & Status Filter Toolbar */}
      <div
        className="rounded-xl border p-3 flex flex-col lg:flex-row lg:items-center gap-3"
        style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
      >
        <div className="relative flex-1">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: 'var(--muted-foreground)' }}
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by Request ID, model, or query text..."
            className="w-full pl-9 pr-8 py-2 text-xs sm:text-sm rounded-lg border focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
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
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-[var(--muted)]"
              style={{ color: 'var(--muted-foreground)' }}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div
          role="group"
          aria-label="Filter cache status"
          className="inline-flex flex-wrap items-center gap-1 p-1 rounded-lg border"
          style={{ backgroundColor: 'var(--background)', borderColor: 'var(--border)' }}
        >
          {STATUS_FILTERS.map((opt) => {
            const active = statusFilter === opt.id;
            const count = statusCounts[opt.id] ?? 0;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setStatusFilter(opt.id)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition cursor-pointer"
                style={
                  active
                    ? { backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }
                    : { color: 'var(--muted-foreground)' }
                }
              >
                <span>{opt.label}</span>
                <span className="text-[10px] opacity-80 tabular-nums">({count})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Logs Table */}
      <div
        className="rounded-xl border overflow-hidden"
        style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
      >
        {isLoading ? (
          <div className="p-12 text-center text-xs" style={{ color: 'var(--muted-foreground)' }}>
            Loading request logs...
          </div>
        ) : logs.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <Activity className="w-8 h-8 mx-auto" style={{ color: 'var(--muted-foreground)' }} />
            <h3 className="text-sm font-semibold" style={{ color: 'var(--foreground)' }}>
              No Matching Requests
            </h3>
            <p className="text-xs max-w-sm mx-auto" style={{ color: 'var(--muted-foreground)' }}>
              Send prompts in the AI Playground or adjust your search/filter to inspect Exact Hit, Semantic Hit, or Miss outcomes.
            </p>
          </div>
        ) : (
          <div className="custom-scrollbar max-h-[calc(100vh-340px)] min-h-[260px] overflow-y-auto overflow-x-auto">
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
                  <th className="px-3 py-3">Req ID</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3">Query</th>
                  <th className="px-3 py-3">Model</th>
                  <th className="px-3 py-3">Cache vs LLM</th>
                  <th className="px-3 py-3">Tokens (In / Out)</th>
                  <th className="px-3 py-3 text-right">Total</th>
                  <th className="px-3 py-3 text-right">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: 'var(--border)' }}>
                {logs.map((item) => {
                  const isHit = item.cache_status === 'exact_hit' || item.cache_status === 'semantic_hit';
                  const reqId = item.request_id || `req-${item.id.slice(0, 8)}`;
                  const cacheMs = item.cache_lookup_latency_ms ?? 1;
                  const llmMs =
                    item.llm_latency_ms ??
                    (isHit ? 0 : Math.max(0, (item.total_latency_ms ?? 0) - cacheMs));

                  return (
                    <tr
                      key={item.id}
                      onClick={() => setSelectedLog(item)}
                      className="cursor-pointer transition-colors hover:bg-[var(--muted)]/45"
                    >
                      <td
                        className="px-3 py-2.5 font-mono text-[11px] whitespace-nowrap"
                        style={{ color: 'var(--muted-foreground)' }}
                      >
                        {reqId.slice(0, 12)}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span
                          className="inline-flex items-center px-2 py-0.5 rounded-full font-semibold text-[10px] uppercase"
                          style={getBadgeStyle(item.cache_status)}
                        >
                          {getBadgeLabel(item.cache_status)}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 max-w-[260px] relative group">
                        <div
                          className="truncate font-medium"
                          style={{ color: 'var(--foreground)' }}
                        >
                          {item.query_preview}
                        </div>
                        <div
                          className="pointer-events-none hidden group-hover:block absolute left-3 top-full z-30 mt-1 w-80 rounded-xl border p-3 text-xs shadow-lg whitespace-normal break-words"
                          style={{
                            backgroundColor: 'var(--card)',
                            borderColor: 'var(--border)',
                            color: 'var(--foreground)',
                          }}
                        >
                          {item.query_preview}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span
                          className="font-mono text-[11px]"
                          style={{ color: 'var(--muted-foreground)' }}
                        >
                          {item.model}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[11px] whitespace-nowrap">
                        <span style={{ color: 'var(--foreground)' }}>Cache: {cacheMs}ms</span>
                        <span className="mx-1" style={{ color: 'var(--muted-foreground)' }}>
                          ·
                        </span>
                        <span style={{ color: 'var(--muted-foreground)' }}>LLM: {llmMs}ms</span>
                      </td>
                      <td
                        className="px-3 py-2.5 whitespace-nowrap tabular-nums"
                        style={{ color: 'var(--foreground)' }}
                      >
                        In: <span className="font-semibold">{item.input_tokens}</span> · Out:{' '}
                        <span className="font-semibold">{item.output_tokens}</span>
                        {isHit && item.tokens_saved > 0 && (
                          <span className="ml-1.5 font-medium" style={{ color: 'var(--hit-text)' }}>
                            (+{item.tokens_saved})
                          </span>
                        )}
                      </td>
                      <td
                        className="px-3 py-2.5 font-mono font-semibold whitespace-nowrap text-right tabular-nums"
                        style={{ color: 'var(--foreground)' }}
                      >
                        {item.total_latency_ms}ms
                      </td>
                      <td
                        className="px-3 py-2.5 whitespace-nowrap text-right tabular-nums"
                        style={{ color: 'var(--muted-foreground)' }}
                      >
                        {new Date(item.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <TelemetryTraceModal
        activeLog={activeLog}
        inspecting={inspecting}
        onClose={() => setSelectedLog(null)}
      />
    </div>
  );
}
