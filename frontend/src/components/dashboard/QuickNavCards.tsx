'use client';

import React from 'react';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

const LINKS = [
  {
    href: '/analytics',
    title: 'Cache Analytics',
    description: 'Review P50/P95/P99 latency and token savings over time.',
  },
  {
    href: '/models',
    title: 'Model Management',
    description: 'Compare hit rates, token consumption, and latency per model.',
  },
  {
    href: '/logs',
    title: 'Request Logs',
    description: 'Audit exact hits, semantic hits, misses, and guardrail events.',
  },
];

export function QuickNavCards() {
  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-3">
      <h2 className="text-sm font-medium text-[var(--foreground)]">More workspace views</h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {LINKS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="group rounded-lg border border-[var(--border)] bg-[var(--background)]/60 p-4 transition-colors hover:bg-[var(--muted)]/60"
          >
            <div className="flex items-center justify-between text-xs font-medium text-[var(--foreground)]">
              <span>{item.title}</span>
              <ArrowRight
                className="h-3.5 w-3.5 text-[var(--muted-foreground)] transition-transform group-hover:translate-x-0.5"
                strokeWidth={1.5}
              />
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--muted-foreground)]">
              {item.description}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}
