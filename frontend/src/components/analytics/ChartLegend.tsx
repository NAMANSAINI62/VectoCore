'use client';

import React from 'react';

export interface ChartLegendItem {
  label: string;
  color: string;
  value?: string | number;
}

export function ChartLegend({ items }: { items: ChartLegendItem[] }) {
  if (!items.length) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] font-medium text-[var(--muted-foreground)]">
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full border border-black/10"
            style={{ backgroundColor: item.color }}
            aria-hidden="true"
          />
          <span className="text-[var(--foreground)]">{item.label}</span>
          {item.value !== undefined && (
            <span className="font-mono font-semibold text-[var(--muted-foreground)]">
              ({item.value})
            </span>
          )}
        </span>
      ))}
    </div>
  );
}
