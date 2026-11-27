'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react';
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react';

export const DATE_PRESETS: Array<{ label: string; days: number | undefined }> = [
  { label: 'All time', days: undefined },
  { label: '7D', days: 7 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
];

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'] as const;

function toIsoDate(year: number, monthIndex: number, day: number): string {
  return `${year}-${String(monthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function getLocalTodayIso(): string {
  const now = new Date();
  return toIsoDate(now.getFullYear(), now.getMonth(), now.getDate());
}

function formatShortDate(iso: string): string {
  if (!iso) return 'Select';
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export interface DateRangeFilterProps {
  selectedDays: number | undefined;
  appliedCustom: { start: string; end: string } | null;
  defaultStartDate?: string | null;
  onSelectPreset: (days: number | undefined) => void;
  onApplyCustom: (range: { start: string; end: string } | null) => void;
}

export function DateRangeFilter({
  selectedDays,
  appliedCustom,
  defaultStartDate,
  onSelectPreset,
  onApplyCustom,
}: DateRangeFilterProps) {
  const todayIso = getLocalTodayIso();
  const minDate = defaultStartDate || undefined;

  const [customStart, setCustomStart] = useState(appliedCustom?.start ?? defaultStartDate ?? '');
  const [customEnd, setCustomEnd] = useState(appliedCustom?.end ?? todayIso);
  const [pickingField, setPickingField] = useState<'start' | 'end'>('start');

  const initialRef = useMemo(() => {
    const base = (appliedCustom?.end || todayIso).split('-').map(Number);
    return { year: base[0] || new Date().getFullYear(), month: (base[1] || 1) - 1 };
  }, [appliedCustom?.end, todayIso]);

  const [viewYear, setViewYear] = useState(initialRef.year);
  const [viewMonth, setViewMonth] = useState(initialRef.month);

  const appliedStart = appliedCustom?.start;
  const appliedEnd = appliedCustom?.end;

  useEffect(() => {
    if (appliedStart !== undefined || appliedEnd !== undefined) {
      setCustomStart(appliedStart || defaultStartDate || '');
      setCustomEnd(appliedEnd || todayIso);
    }
  }, [appliedStart, appliedEnd, defaultStartDate, todayIso]);

  useEffect(() => {
    if (appliedStart === undefined && appliedEnd === undefined && defaultStartDate) {
      setCustomStart((prev) => prev || defaultStartDate);
    }
  }, [appliedStart, appliedEnd, defaultStartDate]);

  const [todayYear, todayMonth] = useMemo(() => {
    const [y, m] = todayIso.split('-').map(Number);
    return [y, m - 1];
  }, [todayIso]);

  const minYearMonth = useMemo(() => {
    if (!minDate) return null;
    const [y, m] = minDate.split('-').map(Number);
    return y && m ? { year: y, month: m - 1 } : null;
  }, [minDate]);

  const canGoPrev =
    !minYearMonth || viewYear > minYearMonth.year || (viewYear === minYearMonth.year && viewMonth > minYearMonth.month);
  const canGoNext = viewYear < todayYear || (viewYear === todayYear && viewMonth < todayMonth);

  const goPrevMonth = () => {
    if (!canGoPrev) return;
    if (viewMonth === 0) {
      setViewYear((y) => y - 1);
      setViewMonth(11);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const goNextMonth = () => {
    if (!canGoNext) return;
    if (viewMonth === 11) {
      setViewYear((y) => y + 1);
      setViewMonth(0);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  const monthLabel = new Date(viewYear, viewMonth, 1).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });

  const calendarCells = useMemo(() => {
    const firstWeekday = new Date(viewYear, viewMonth, 1).getDay();
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const cells: Array<{ day: number; iso: string } | null> = [];
    for (let i = 0; i < firstWeekday; i++) {
      cells.push(null);
    }
    for (let d = 1; d <= daysInMonth; d++) {
      cells.push({ day: d, iso: toIsoDate(viewYear, viewMonth, d) });
    }
    return cells;
  }, [viewYear, viewMonth]);

  const isDateDisabled = (iso: string): boolean => {
    if (minDate && iso < minDate) return true;
    if (iso > todayIso) return true;
    if (pickingField === 'start' && customEnd && iso > customEnd) return true;
    if (pickingField === 'end' && customStart && iso < customStart) return true;
    return false;
  };

  const handleSelectDay = (iso: string) => {
    if (isDateDisabled(iso)) return;
    if (pickingField === 'start') {
      setCustomStart(iso);
    } else {
      setCustomEnd(iso);
    }
  };

  const handleSubmit = (e: React.FormEvent, close: () => void) => {
    e.preventDefault();
    if (!customStart && !customEnd) return;
    if (minDate && customStart && customStart < minDate) return;
    if (customEnd && customEnd > todayIso) return;
    if (customStart && customEnd && customEnd < customStart) return;
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
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-150 cursor-pointer ${
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
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition-colors focus:outline-none cursor-pointer ${
            appliedCustom
              ? 'border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-foreground)]'
              : 'border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] hover:bg-[var(--muted)]'
          }`}
        >
          <Calendar className="h-3.5 w-3.5" aria-hidden="true" />
          <span>
            {appliedCustom
              ? `${formatShortDate(appliedCustom.start)} → ${formatShortDate(appliedCustom.end)}`
              : 'Custom Range'}
          </span>
        </PopoverButton>

        <PopoverPanel
          className="absolute right-0 top-full z-40 mt-2 w-[268px] max-w-[calc(100vw-1.5rem)] rounded-2xl border p-2.5 backdrop-blur-2xl focus:outline-none animate-in fade-in zoom-in-95 duration-150"
          style={{
            background: 'color-mix(in srgb, var(--card) 82%, transparent)',
            borderColor: 'var(--border)',
            boxShadow: '0 20px 44px rgba(15, 23, 42, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.3)',
          }}
        >
          {({ close }) => (
            <form onSubmit={(e) => handleSubmit(e, close)} className="space-y-2 select-none">
              {/* Top Start / End Pill Selector */}
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  onClick={() => setPickingField('start')}
                  className={`rounded-xl border px-2 py-1 text-left transition-colors cursor-pointer ${
                    pickingField === 'start'
                      ? 'border-[var(--accent)] bg-[var(--accent)]/12'
                      : 'border-[var(--border)] bg-[var(--background)]/55 hover:bg-[var(--background)]/80'
                  }`}
                >
                  <span className="block text-[9px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                    Start Date
                  </span>
                  <span className="block truncate text-[11px] font-semibold text-[var(--foreground)]">
                    {formatShortDate(customStart)}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setPickingField('end')}
                  className={`rounded-xl border px-2 py-1 text-left transition-colors cursor-pointer ${
                    pickingField === 'end'
                      ? 'border-[var(--accent)] bg-[var(--accent)]/12'
                      : 'border-[var(--border)] bg-[var(--background)]/55 hover:bg-[var(--background)]/80'
                  }`}
                >
                  <span className="block text-[9px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                    End Date
                  </span>
                  <span className="block truncate text-[11px] font-semibold text-[var(--foreground)]">
                    {formatShortDate(customEnd)}
                  </span>
                </button>
              </div>

              {/* Month Header */}
              <div className="flex items-center justify-between px-0.5">
                <button
                  type="button"
                  onClick={goPrevMonth}
                  disabled={!canGoPrev}
                  aria-label="Previous month"
                  className="flex h-6 w-6 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--background)]/60 text-[var(--foreground)] transition hover:bg-[var(--muted)] disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <span className="text-[11.5px] font-semibold text-[var(--foreground)]">{monthLabel}</span>
                <button
                  type="button"
                  onClick={goNextMonth}
                  disabled={!canGoNext}
                  aria-label="Next month"
                  className="flex h-6 w-6 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--background)]/60 text-[var(--foreground)] transition hover:bg-[var(--muted)] disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Calendar Grid */}
              <div>
                <div className="grid grid-cols-7 gap-0.5 mb-0.5">
                  {WEEKDAYS.map((wd) => (
                    <div
                      key={wd}
                      className="text-center text-[9.5px] font-semibold text-[var(--muted-foreground)] py-0.5"
                    >
                      {wd}
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-7 gap-0.5">
                  {calendarCells.map((cell, idx) => {
                    if (!cell) {
                      return <div key={`empty-${idx}`} className="h-7" />;
                    }
                    const disabled = isDateDisabled(cell.iso);
                    const isStart = cell.iso === customStart;
                    const isEnd = cell.iso === customEnd;
                    const isSelected = isStart || isEnd;
                    const inRange = Boolean(customStart && customEnd && cell.iso > customStart && cell.iso < customEnd);
                    const isToday = cell.iso === todayIso;

                    return (
                      <button
                        key={cell.iso}
                        type="button"
                        disabled={disabled}
                        onClick={() => handleSelectDay(cell.iso)}
                        className={`h-7 w-full rounded-lg text-[11px] tabular-nums transition-colors ${
                          isSelected
                            ? 'bg-[var(--accent)] text-[var(--accent-foreground)] font-semibold shadow-xs'
                            : inRange
                            ? 'bg-[var(--accent)]/15 text-[var(--foreground)] font-medium hover:bg-[var(--accent)]/25'
                            : disabled
                            ? 'text-[var(--muted-foreground)] opacity-30 cursor-not-allowed'
                            : 'text-[var(--foreground)] hover:bg-[var(--muted)] cursor-pointer'
                        } ${isToday && !isSelected ? 'ring-1 ring-[var(--accent)]/60 font-semibold' : ''}`}
                      >
                        {cell.day}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Footer */}
              <div
                className="flex items-center justify-between border-t pt-2"
                style={{ borderColor: 'var(--border)' }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setCustomStart(defaultStartDate ?? '');
                    setCustomEnd(todayIso);
                    setPickingField('start');
                    onApplyCustom(null);
                    close();
                  }}
                  className="text-[11px] font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
                >
                  Reset
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-[var(--accent)] px-3 py-1 text-[11px] font-semibold text-[var(--accent-foreground)] transition hover:opacity-90 cursor-pointer"
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
