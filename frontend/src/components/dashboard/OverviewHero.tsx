'use client';

import React from 'react';
import Link from 'next/link';
import { Database, MessageSquare } from 'lucide-react';
import { CacheStatsResponse } from '@/store/cacheApi';

export interface OverviewHeroProps {
  stats?: CacheStatsResponse;
  isLoading?: boolean;
}

export function OverviewHero(_props: OverviewHeroProps) {
  return (
    <div
      className="p-6 sm:p-8 rounded-2xl border shadow-xs transition-colors duration-200"
      style={{
        background: 'var(--hero-bg)',
        borderColor: 'var(--hero-border)',
        color: 'var(--hero-text)',
      }}
    >
      <div className="max-w-2xl space-y-3">
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight" style={{ color: 'var(--hero-text)' }}>
          High-Performance AI Semantic Caching
        </h1>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--hero-subtext)' }}>
          Eliminate redundant LLM inferences with exact caching and
          multilingual vector semantic search across English, Hindi, and Hinglish.
        </p>
        <div className="pt-2 flex flex-wrap gap-3">
          <Link
            href="/playground"
            className="inline-flex items-center gap-2 px-4 py-2 font-semibold rounded-lg text-xs transition hover:opacity-90 shadow-xs"
            style={{
              backgroundColor: 'var(--hero-btn-primary-bg)',
              color: 'var(--hero-btn-primary-text)',
            }}
          >
            <MessageSquare className="w-4 h-4" />
            Open AI Playground
          </Link>
          <Link
            href="/cache"
            className="inline-flex items-center gap-2 px-4 py-2 font-medium rounded-lg text-xs border transition hover:opacity-90"
            style={{
              backgroundColor: 'var(--hero-btn-secondary-bg)',
              color: 'var(--hero-btn-secondary-text)',
              borderColor: 'var(--hero-border)',
            }}
          >
            <Database className="w-4 h-4" />
            Explore Cache
          </Link>
        </div>
      </div>
    </div>
  );
}
