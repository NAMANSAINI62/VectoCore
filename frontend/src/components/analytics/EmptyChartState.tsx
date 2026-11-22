'use client';

import React from 'react';
import { BarChart3 } from 'lucide-react';

export interface EmptyChartStateProps {
  title?: string;
  message?: string;
  heightClass?: string;
}

export function EmptyChartState({
  title = 'No Telemetry Available',
  message = 'Send queries in the AI Playground to populate real telemetry for this visualization.',
  heightClass = 'h-56',
}: EmptyChartStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border)] bg-[var(--background)]/40 px-4 text-center ${heightClass}`}
    >
      <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--muted)] text-[var(--muted-foreground)]">
        <BarChart3 className="h-4 w-4" aria-hidden="true" />
      </div>
      <p className="text-xs font-semibold text-[var(--foreground)]">{title}</p>
      <p className="mt-1 max-w-xs text-[11px] leading-relaxed text-[var(--muted-foreground)]">
        {message}
      </p>
    </div>
  );
}
