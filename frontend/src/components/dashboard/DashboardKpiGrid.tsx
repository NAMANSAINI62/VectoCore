'use client';

import React from 'react';
import { ArrowDownLeft, ArrowUpRight, Database, Layers, Zap } from 'lucide-react';
import { CacheStatsResponse } from '@/store/cacheApi';

export interface DashboardKpiGridProps {
  stats?: CacheStatsResponse;
  isLoading: boolean;
}

export function DashboardKpiGrid({ stats, isLoading }: DashboardKpiGridProps) {
  const exactHits = stats?.exact_hits ?? 0;
  const semanticHits = stats?.semantic_hits ?? 0;
  const totalHits = exactHits + semanticHits;
  const exactShare = totalHits > 0 ? Math.round((exactHits / totalHits) * 100) : 0;

  const totalInput = stats?.total_input_tokens ?? 0;
  const totalOutput = stats?.total_output_tokens ?? 0;
  const totalConsumed = totalInput + totalOutput;
  const inputShare = totalConsumed > 0 ? Math.round((totalInput / totalConsumed) * 100) : 0;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div
        className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-2.5"
        style={{ borderTopWidth: '2px', borderTopColor: 'var(--accent)' }}
      >
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-medium">Tokens saved</span>
          <Zap className="h-4 w-4 text-[var(--accent)]" strokeWidth={1.5} />
        </div>
        <div className="text-3xl font-medium tracking-tight tabular-nums text-[var(--foreground)]">
          {isLoading ? '—' : (stats?.real_tokens_saved ?? 0).toLocaleString()}
        </div>
        <p className="text-xs tabular-nums text-[var(--muted-foreground)]">
          In {(stats?.input_tokens_saved ?? 0).toLocaleString()} · Out {(stats?.output_tokens_saved ?? 0).toLocaleString()}
        </p>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-2.5">
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-medium">Cache hit rate</span>
          <Layers className="h-4 w-4" strokeWidth={1.5} />
        </div>
        <div className="text-3xl font-medium tracking-tight tabular-nums text-[var(--foreground)]">
          {isLoading ? '—' : `${stats?.hit_rate_pct ?? 0}%`}
        </div>
        <div className="space-y-1.5">
          <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-[var(--muted)]">
            <div style={{ width: `${exactShare}%`, backgroundColor: 'var(--chart-exact)' }} />
            <div style={{ width: `${totalHits > 0 ? 100 - exactShare : 0}%`, backgroundColor: 'var(--chart-semantic)' }} />
          </div>
          <p className="text-xs tabular-nums text-[var(--muted-foreground)]">
            {exactHits} exact · {semanticHits} semantic
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-2.5">
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-medium">Active cache entries</span>
          <Database className="h-4 w-4" strokeWidth={1.5} />
        </div>
        <div className="text-3xl font-medium tracking-tight tabular-nums text-[var(--foreground)]">
          {isLoading ? '—' : (stats?.total_entries_count ?? 0).toLocaleString()}
        </div>
        <p className="text-xs text-[var(--muted-foreground)]">
          Indexed in pgvector &amp; Redis (48h TTL)
        </p>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-2.5">
        <div className="flex items-center justify-between text-[var(--muted-foreground)]">
          <span className="text-xs font-medium">Tokens consumed</span>
          <div className="flex items-center gap-0.5">
            <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={1.5} />
            <ArrowDownLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          </div>
        </div>
        <div className="text-3xl font-medium tracking-tight tabular-nums text-[var(--foreground)]">
          {isLoading ? '—' : totalConsumed.toLocaleString()}
        </div>
        <div className="space-y-1.5">
          <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-[var(--muted)]">
            <div style={{ width: `${inputShare}%`, backgroundColor: 'var(--chart-input)' }} />
            <div style={{ width: `${totalConsumed > 0 ? 100 - inputShare : 0}%`, backgroundColor: 'var(--chart-output)' }} />
          </div>
          <p className="text-xs tabular-nums text-[var(--muted-foreground)]">
            In {totalInput.toLocaleString()} · Out {totalOutput.toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}
