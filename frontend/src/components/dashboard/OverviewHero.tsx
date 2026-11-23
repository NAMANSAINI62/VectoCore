'use client';

import React from 'react';
import Link from 'next/link';
import { Database, MessageSquare } from 'lucide-react';
import { CacheStatsResponse } from '@/store/cacheApi';

export interface OverviewHeroProps {
  stats?: CacheStatsResponse;
  isLoading?: boolean;
}

export function OverviewHero({ stats, isLoading }: OverviewHeroProps) {
  const totalRequests = stats?.total_requests ?? 0;
  const avgHitMs = stats?.avg_hit_latency_ms ?? 0;
  const avgMissMs = stats?.avg_miss_latency_ms ?? 0;
  const speedup = avgHitMs > 0 && avgMissMs > 0 ? `${(avgMissMs / avgHitMs).toFixed(1)}x` : '—';

  return (
    <section
      className="rounded-2xl border p-6 sm:p-7 transition-colors duration-150"
      style={{
        background: 'var(--hero-bg)',
        borderColor: 'var(--hero-border)',
        color: 'var(--hero-text)',
      }}
    >
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-xl space-y-2.5">
          <h1 className="text-2xl font-medium tracking-tight" style={{ color: 'var(--hero-text)' }}>
            Semantic Cache Overview
          </h1>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--hero-subtext)' }}>
            Exact Redis lookups and multilingual vector matching across English, Hindi, and Hinglish.
          </p>
          <div className="flex flex-wrap items-center gap-2.5 pt-1.5">
            <Link
              href="/playground"
              className="inline-flex h-9 items-center gap-2 rounded-lg px-4 text-xs font-semibold transition-opacity hover:opacity-90"
              style={{
                backgroundColor: 'var(--hero-btn-primary-bg)',
                color: 'var(--hero-btn-primary-text)',
              }}
            >
              <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.75} />
              <span>Open Playground</span>
            </Link>
            <Link
              href="/cache"
              className="inline-flex h-9 items-center gap-2 rounded-lg border px-4 text-xs font-medium transition-opacity hover:opacity-90"
              style={{
                backgroundColor: 'var(--hero-btn-secondary-bg)',
                color: 'var(--hero-btn-secondary-text)',
                borderColor: 'var(--hero-border)',
              }}
            >
              <Database className="h-3.5 w-3.5" strokeWidth={1.75} />
              <span>Explore Cache</span>
            </Link>
          </div>
        </div>

        {/* Non-duplicative Hero Telemetry Strip */}
        <div
          className="grid grid-cols-3 divide-x rounded-xl border px-2 py-3.5 sm:px-4"
          style={{
            backgroundColor: 'rgba(255, 255, 255, 0.7)',
            borderColor: 'var(--hero-border)',
          }}
        >
          <div className="px-3 sm:px-4 space-y-1">
            <p className="text-[11px]" style={{ color: 'var(--hero-subtext)' }}>
              Total requests
            </p>
            <p className="text-xl font-medium tabular-nums" style={{ color: 'var(--hero-text)' }}>
              {isLoading ? '—' : totalRequests.toLocaleString()}
            </p>
          </div>
          <div className="px-3 sm:px-4 space-y-1" style={{ borderColor: 'var(--hero-border)' }}>
            <p className="text-[11px]" style={{ color: 'var(--hero-subtext)' }}>
              Speedup
            </p>
            <p className="text-xl font-medium tabular-nums" style={{ color: 'var(--hero-pill-text)' }}>
              {isLoading ? '—' : speedup}
            </p>
          </div>
          <div className="px-3 sm:px-4 space-y-1" style={{ borderColor: 'var(--hero-border)' }}>
            <p className="text-[11px]" style={{ color: 'var(--hero-subtext)' }}>
              Calls avoided
            </p>
            <p className="text-xl font-medium tabular-nums" style={{ color: 'var(--hero-text)' }}>
              {isLoading ? '—' : (stats?.llm_calls_avoided ?? 0).toLocaleString()}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
