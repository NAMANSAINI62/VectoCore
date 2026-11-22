'use client';

import React from 'react';
import { ChartHeader } from '@/components/analytics/ChartHeader';
import { EmptyChartState } from '@/components/analytics/EmptyChartState';
import { AlertCircle } from 'lucide-react';

export interface ChartContainerProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  legend?: React.ReactNode;
  footer?: React.ReactNode;
  isLoading?: boolean;
  isError?: boolean;
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyMessage?: string;
  heightClass?: string;
  className?: string;
  children: React.ReactNode;
}

export function ChartContainer({
  title,
  description,
  icon,
  badge,
  action,
  legend,
  footer,
  isLoading = false,
  isError = false,
  isEmpty = false,
  emptyTitle,
  emptyMessage,
  heightClass = 'h-64',
  className = '',
  children,
}: ChartContainerProps) {
  return (
    <section
      className={`flex flex-col justify-between rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-xs space-y-4 transition-colors ${className}`}
    >
      <div className="space-y-2.5">
        <ChartHeader
          title={title}
          description={description}
          icon={icon}
          badge={badge}
          action={action}
        />
        {legend}
      </div>

      {isLoading ? (
        <div
          className={`animate-pulse rounded-xl border border-[var(--border)] bg-[var(--muted)]/55 ${heightClass}`}
        />
      ) : isError ? (
        <div
          className={`flex flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border)] bg-[var(--miss-bg)]/30 px-4 text-center ${heightClass}`}
        >
          <AlertCircle className="mb-2 h-5 w-5 text-[var(--miss-text)]" aria-hidden="true" />
          <p className="text-xs font-semibold text-[var(--foreground)]">Unable to load telemetry</p>
          <p className="mt-1 text-[11px] text-[var(--muted-foreground)]">
            Try refreshing the page to fetch the latest metrics.
          </p>
        </div>
      ) : isEmpty ? (
        <EmptyChartState title={emptyTitle} message={emptyMessage} heightClass={heightClass} />
      ) : (
        <div className={`w-full min-w-0 ${heightClass}`}>{children}</div>
      )}

      {footer ? (
        <div className="border-t border-[var(--border)] pt-3 text-xs text-[var(--muted-foreground)]">
          {footer}
        </div>
      ) : null}
    </section>
  );
}
