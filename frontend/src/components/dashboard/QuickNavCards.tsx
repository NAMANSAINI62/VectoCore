'use client';

import React from 'react';
import Link from 'next/link';
import { ArrowRight, TrendingUp } from 'lucide-react';

export function QuickNavCards() {
  return (
    <div className="bg-[var(--card)] p-6 rounded-2xl border border-[var(--border)] shadow-xs space-y-4">
      <h2 className="text-base font-bold text-[var(--foreground)] flex items-center gap-2">
        <TrendingUp className="w-5 h-5 text-[var(--accent)]" />
        Quick Navigation & Tools
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
        <Link
          href="/playground"
          className="p-4 rounded-xl border border-[var(--border)] bg-[var(--background)]/50 hover:border-[var(--accent)] hover:bg-[var(--muted)]/70 transition group"
        >
          <div className="font-semibold text-[var(--foreground)] group-hover:text-[var(--accent)] transition flex items-center justify-between">
            AI Chat Playground
            <ArrowRight className="w-4 h-4 text-[var(--muted-foreground)] group-hover:translate-x-1 group-hover:text-[var(--accent)] transition" />
          </div>
          <p className="text-[var(--muted-foreground)] mt-1">
            Chat across configured LLM providers with real-time SSE cache telemetry.
          </p>
        </Link>

        <Link
          href="/cache"
          className="p-4 rounded-xl border border-[var(--border)] bg-[var(--background)]/50 hover:border-[var(--accent)] hover:bg-[var(--muted)]/70 transition group"
        >
          <div className="font-semibold text-[var(--foreground)] group-hover:text-[var(--accent)] transition flex items-center justify-between">
            Cache Explorer
            <ArrowRight className="w-4 h-4 text-[var(--muted-foreground)] group-hover:translate-x-1 group-hover:text-[var(--accent)] transition" />
          </div>
          <p className="text-[var(--muted-foreground)] mt-1">
            Search, filter, inspect and invalidate cached prompts and responses.
          </p>
        </Link>

        <Link
          href="/analytics"
          className="p-4 rounded-xl border border-[var(--border)] bg-[var(--background)]/50 hover:border-[var(--accent)] hover:bg-[var(--muted)]/70 transition group"
        >
          <div className="font-semibold text-[var(--foreground)] group-hover:text-[var(--accent)] transition flex items-center justify-between">
            Cache Analytics & Performance
            <ArrowRight className="w-4 h-4 text-[var(--muted-foreground)] group-hover:translate-x-1 group-hover:text-[var(--accent)] transition" />
          </div>
          <p className="text-[var(--muted-foreground)] mt-1">
            Track P50/P95/P99 latency graphs, hit/miss trends, and input/output token usage.
          </p>
        </Link>
      </div>
    </div>
  );
}
