'use client';

import React from 'react';

export interface ChartHeaderProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  action?: React.ReactNode;
}

export function ChartHeader({ title, description, icon, badge, action }: ChartHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2.5">
      <div className="min-w-0 space-y-0.5">
        <h2 className="flex items-center gap-2 text-sm sm:text-base font-bold text-[var(--foreground)]">
          {icon ? <span className="shrink-0 text-[var(--accent)]">{icon}</span> : null}
          <span className="truncate">{title}</span>
        </h2>
        {description ? (
          <p className="text-xs text-[var(--muted-foreground)] leading-relaxed">{description}</p>
        ) : null}
      </div>

      {(badge || action) && (
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {badge}
          {action}
        </div>
      )}
    </div>
  );
}
