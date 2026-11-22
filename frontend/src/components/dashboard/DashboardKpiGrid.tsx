'use client';

import React from 'react';
import {
  ArrowDownLeft,
  ArrowUpRight,
  Database,
  Layers,
  Zap,
} from 'lucide-react';
import { CacheStatsResponse } from '@/store/cacheApi';

export interface DashboardKpiGridProps {
  stats?: CacheStatsResponse;
  isLoading: boolean;
}

export function DashboardKpiGrid({ stats, isLoading }: DashboardKpiGridProps) {
  const exactHits = stats?.exact_hits ?? 0;
  const semanticHits = stats?.semantic_hits ?? 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div className="bg-[var(--card)] p-5 rounded-2xl border border-[var(--border)] shadow-xs space-y-2 transition-colors">
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-semibold uppercase tracking-wider">Real Tokens Saved</span>
          <div className="p-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
            <Zap className="w-4 h-4" />
          </div>
        </div>
        <div className="text-3xl font-extrabold tabular-nums" style={{ color: 'var(--stat-number)' }}>
          {isLoading ? '...' : (stats?.real_tokens_saved ?? 0).toLocaleString()}
        </div>
        <p className="text-xs text-[var(--muted-foreground)]">
          Input saved: {(stats?.input_tokens_saved ?? 0).toLocaleString()} · Output saved:{' '}
          {(stats?.output_tokens_saved ?? 0).toLocaleString()}
        </p>
      </div>

      <div className="bg-[var(--card)] p-5 rounded-2xl border border-[var(--border)] shadow-xs space-y-2 transition-colors">
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-semibold uppercase tracking-wider">Cache Hit Rate</span>
          <div className="p-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
            <Layers className="w-4 h-4" />
          </div>
        </div>
        <div className="text-3xl font-extrabold tabular-nums" style={{ color: 'var(--stat-number)' }}>
          {isLoading ? '...' : `${stats?.hit_rate_pct ?? 0}%`}
        </div>
        <p className="text-xs text-[var(--muted-foreground)]">
          {exactHits} exact · {semanticHits} semantic · {stats?.llm_calls_avoided ?? 0} LLM calls avoided
        </p>
      </div>

      <div className="bg-[var(--card)] p-5 rounded-2xl border border-[var(--border)] shadow-xs space-y-2 transition-colors">
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-semibold uppercase tracking-wider">Active Cache Entries</span>
          <div className="p-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
            <Database className="w-4 h-4" />
          </div>
        </div>
        <div className="text-3xl font-extrabold tabular-nums" style={{ color: 'var(--stat-number)' }}>
          {isLoading ? '...' : stats?.total_entries_count ?? 0}
        </div>
        <p className="text-xs text-[var(--muted-foreground)]">
          Indexed in vector similarity and exact cache
        </p>
      </div>

      <div className="bg-[var(--card)] p-5 rounded-2xl border border-[var(--border)] shadow-xs space-y-2 transition-colors">
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-semibold uppercase tracking-wider">Input Tokens Consumed</span>
          <div className="p-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
            <ArrowUpRight className="w-4 h-4" />
          </div>
        </div>
        <div className="text-3xl font-extrabold tabular-nums" style={{ color: 'var(--stat-number)' }}>
          {isLoading ? '...' : (stats?.total_input_tokens ?? 0).toLocaleString()}
        </div>
        <p className="text-xs text-[var(--muted-foreground)]">
          Saved: {(stats?.input_tokens_saved ?? 0).toLocaleString()}
        </p>
      </div>

      <div className="bg-[var(--card)] p-5 rounded-2xl border border-[var(--border)] shadow-xs space-y-2 transition-colors">
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-semibold uppercase tracking-wider">Output Tokens Consumed</span>
          <div className="p-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
            <ArrowDownLeft className="w-4 h-4" />
          </div>
        </div>
        <div className="text-3xl font-extrabold tabular-nums" style={{ color: 'var(--stat-number)' }}>
          {isLoading ? '...' : (stats?.total_output_tokens ?? 0).toLocaleString()}
        </div>
        <p className="text-xs text-[var(--muted-foreground)]">
          Saved: {(stats?.output_tokens_saved ?? 0).toLocaleString()}
        </p>
      </div>
    </div>
  );
}
