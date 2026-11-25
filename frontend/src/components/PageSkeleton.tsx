'use client';

import React from 'react';
import { Layers } from 'lucide-react';

export function WorkspaceContentSkeleton() {
  return (
    <div className="space-y-6 animate-pulse" aria-busy="true" aria-label="Loading workspace content">
      {/* Hero / Page Header Skeleton */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2.5">
            <div className="h-3 w-28 rounded-full bg-[var(--muted)]" />
            <div className="h-6 w-64 max-w-full rounded-lg bg-[var(--muted)]" />
            <div className="h-3.5 w-96 max-w-full rounded-md bg-[var(--muted)]/80" />
          </div>
          <div className="flex items-center gap-2">
            <div className="h-9 w-24 rounded-lg bg-[var(--muted)]" />
            <div className="h-9 w-28 rounded-lg bg-[var(--muted)]" />
          </div>
        </div>
      </div>

      {/* KPI Grid Skeleton */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, idx) => (
          <div
            key={idx}
            className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="h-3 w-20 rounded bg-[var(--muted)]" />
              <div className="h-6 w-6 rounded-md bg-[var(--muted)]" />
            </div>
            <div className="h-7 w-24 rounded-md bg-[var(--muted)]" />
            <div className="h-2.5 w-28 rounded bg-[var(--muted)]/70" />
          </div>
        ))}
      </div>

      {/* Charts / Main Content Grid Skeleton */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-7 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="h-4 w-40 rounded bg-[var(--muted)]" />
            <div className="h-4 w-20 rounded bg-[var(--muted)]" />
          </div>
          <div className="h-64 w-full rounded-xl bg-[var(--muted)]/60" />
        </div>
        <div className="lg:col-span-5 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="h-4 w-36 rounded bg-[var(--muted)]" />
            <div className="h-4 w-16 rounded bg-[var(--muted)]" />
          </div>
          <div className="h-64 w-full rounded-xl bg-[var(--muted)]/60" />
        </div>
      </div>
    </div>
  );
}

export function WorkspaceShellSkeleton() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--background)] text-[var(--foreground)]">
      {/* Top Header Skeleton */}
      <header className="sticky top-0 z-30 flex h-14 sm:h-16 shrink-0 items-center justify-between border-b border-[var(--border)] bg-[var(--card)]/95 px-3 backdrop-blur sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent)] text-[var(--accent-foreground)]">
            <Layers className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold tracking-tight text-[var(--foreground)]">
            Vector Cache
          </span>
        </div>
        <div className="flex items-center gap-2.5 animate-pulse">
          <div className="h-8 w-24 rounded-lg bg-[var(--muted)]" />
          <div className="h-8 w-20 rounded-lg bg-[var(--muted)]" />
        </div>
      </header>

      {/* Secondary Nav Bar Skeleton */}
      <div className="border-b border-[var(--border)] bg-[var(--card)]/60 px-3 py-2 sm:px-6 lg:px-8">
        <div className="flex items-center gap-2 overflow-hidden animate-pulse">
          {Array.from({ length: 7 }).map((_, idx) => (
            <div key={idx} className="h-7 w-24 shrink-0 rounded-lg bg-[var(--muted)]" />
          ))}
        </div>
      </div>

      {/* Main Content Skeleton */}
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-3 py-5 sm:px-6 lg:px-8">
        <WorkspaceContentSkeleton />
      </main>
    </div>
  );
}
