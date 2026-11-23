'use client';

import React, { useState } from 'react';
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react';
import { Calendar } from 'lucide-react';

export const DATE_PRESETS: Array<{ label: string; days: number | undefined }> = [
  { label: 'All time', days: undefined },
  { label: '7D', days: 7 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
];

export interface DateRangeFilterProps {
  selectedDays: number | undefined;
  appliedCustom: { start: string; end: string } | null;
  onSelectPreset: (days: number | undefined) => void;
  onApplyCustom: (range: { start: string; end: string } | null) => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export function DateRangeFilter({
  selectedDays,
  appliedCustom,
  onSelectPreset,
  onApplyCustom,
}: DateRangeFilterProps) {
  const [customStart, setCustomStart] = useState(appliedCustom?.start ?? '');
  const [customEnd, setCustomEnd] = useState(appliedCustom?.end ?? '');

  const handleSubmit = (e: React.FormEvent, close: () => void) => {
    e.preventDefault();
    if (!customStart && !customEnd) return;
    onApplyCustom({ start: customStart, end: customEnd });
    close();
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div
        role="group"
        aria-label="Date preset"
        className="inline-flex items-center gap-1 rounded-xl border border-[var(--border)] bg-[var(--card)] p-1 shadow-xs"
      >
        {DATE_PRESETS.map((opt) => {
          const active = !appliedCustom && selectedDays === opt.days;
          return (
            <button
              key={opt.label}
              type="button"
              onClick={() => onSelectPreset(opt.days)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-150 ${
                active
                  ? 'bg-[var(--accent)] text-[var(--accent-foreground)] shadow-xs'
                  : 'text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]'
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      <Popover className="relative">
        <PopoverButton
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition-colors focus:outline-none ${
            appliedCustom
              ? 'border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-foreground)]'
              : 'border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] hover:bg-[var(--muted)]'
          }`}
        >
          <Calendar className="h-3.5 w-3.5" aria-hidden="true" />
          <span>
            {appliedCustom
              ? `${appliedCustom.start || 'Start'} → ${appliedCustom.end || 'Now'}`
              : 'Custom Range'}
          </span>
        </PopoverButton>

        <PopoverPanel className="absolute right-0 top-full z-40 mt-2 w-72 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 shadow-xl focus:outline-none">
          {({ close }) => (
            <form onSubmit={(e) => handleSubmit(e, close)} className="space-y-3">
              <p className="text-xs font-semibold text-[var(--foreground)]">Select Date Range</p>
              <div className="space-y-2">
                <label className="block text-[11px] text-[var(--muted-foreground)]">
                  Start Date
                  <input
                    type="date"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-2.5 py-1.5 text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                  />
                </label>
                <label className="block text-[11px] text-[var(--muted-foreground)]">
                  End Date
                  <input
                    type="date"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-2.5 py-1.5 text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                  />
                </label>
              </div>
              <div className="flex items-center justify-between pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setCustomStart('');
                    setCustomEnd('');
                    onApplyCustom(null);
                    close();
                  }}
                  className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                >
                  Reset
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-semibold text-[var(--accent-foreground)] transition hover:opacity-90"
                >
                  Apply Range
                </button>
              </div>
            </form>
          )}
        </PopoverPanel>
      </Popover>
    </div>
  );
}
