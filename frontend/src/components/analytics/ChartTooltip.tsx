'use client';

import React from 'react';
import type { TooltipContentProps } from 'recharts';

export type RechartsTooltipPayload = TooltipContentProps['payload'];
export type TooltipPayloadEntry = RechartsTooltipPayload[number];

export interface ChartTooltipProps {
  active?: boolean;
  payload?: RechartsTooltipPayload;
  label?: string | number;
  valueFormatter?: (value: number, name: string, entry: TooltipPayloadEntry) => string;
  labelFormatter?: (label: string | number, payload?: RechartsTooltipPayload) => string;
  footerRenderer?: (payload: RechartsTooltipPayload) => React.ReactNode;
}

export function ChartTooltip({
  active,
  payload,
  label,
  valueFormatter,
  labelFormatter,
  footerRenderer,
}: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const displayLabel = labelFormatter ? labelFormatter(label ?? '', payload) : String(label ?? '');

  return (
    <div className="min-w-[175px] max-w-[270px] rounded-xl border border-[var(--border)] bg-[var(--card)]/95 px-3 py-2.5 text-xs shadow-lg backdrop-blur-sm">
      {displayLabel ? (
        <div className="mb-1.5 border-b border-[var(--border)] pb-1 font-semibold text-[var(--foreground)] break-words">
          {displayLabel}
        </div>
      ) : null}

      <div className="space-y-1">
        {payload.map((entry, idx) => {
          const scalarVal = Array.isArray(entry.value) ? entry.value[0] : entry.value;
          const rawVal = typeof scalarVal === 'number' ? scalarVal : Number(scalarVal ?? 0);
          const name = String(entry.name ?? entry.dataKey ?? 'Value');
          const formatted = valueFormatter
            ? valueFormatter(Number.isFinite(rawVal) ? rawVal : 0, name, entry)
            : Number.isFinite(rawVal)
              ? rawVal.toLocaleString()
              : String(scalarVal ?? '0');

          return (
            <div key={`${name}-${idx}`} className="flex items-center justify-between gap-3">
              <span className="flex min-w-0 items-center gap-1.5 text-[var(--muted-foreground)]">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: entry.color || 'var(--accent)' }}
                  aria-hidden="true"
                />
                <span className="truncate">{name}</span>
              </span>
              <span className="shrink-0 font-mono font-semibold tabular-nums text-[var(--foreground)]">
                {formatted}
              </span>
            </div>
          );
        })}
      </div>

      {footerRenderer ? (
        <div className="mt-1.5 border-t border-[var(--border)] pt-1.5 text-[11px] text-[var(--muted-foreground)]">
          {footerRenderer(payload)}
        </div>
      ) : null}
    </div>
  );
}
