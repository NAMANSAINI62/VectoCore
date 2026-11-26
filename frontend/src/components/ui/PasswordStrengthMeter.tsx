'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export interface PasswordStrengthResult {
  score: number;
  label: string;
  toneClass: string;
  barColor: string;
}

/**
 * Score a password on every keystroke using length tiers plus digit and symbol checks, clamped 0..4.
 */
export function scorePassword(value: string): PasswordStrengthResult {
  if (!value) {
    return {
      score: 0,
      label: '',
      toneClass: 'text-[var(--muted-foreground)]',
      barColor: 'transparent',
    };
  }

  let rawScore = 0;
  if (value.length >= 6) rawScore += 1;
  if (value.length >= 10) rawScore += 1;
  if (/\d/.test(value)) rawScore += 1;
  if (/[^A-Za-z0-9\s]/.test(value)) rawScore += 1;

  const score = Math.max(0, Math.min(4, rawScore));

  if (score <= 2) {
    return {
      score,
      label: 'Weak',
      toneClass: 'text-rose-500',
      barColor: '#ef4444',
    };
  }

  if (score === 3) {
    return {
      score,
      label: 'Medium',
      toneClass: 'text-amber-500',
      barColor: '#f59e0b',
    };
  }

  return {
    score,
    label: 'Strong',
    toneClass: 'text-emerald-600 dark:text-emerald-400',
    barColor: '#10b981',
  };
}

export interface PasswordStrengthMeterProps {
  value: string;
  className?: string;
}

/**
 * Four-segment password strength meter with spring scaleX(0 -> 1) bar reveal and tinted status label.
 */
export function PasswordStrengthMeter({ value, className }: PasswordStrengthMeterProps) {
  const { score, label, toneClass, barColor } = scorePassword(value);

  return (
    <div className={cn('space-y-1.5', className)} aria-live="polite">
      <div className="grid grid-cols-4 gap-1.5" role="progressbar" aria-valuenow={score} aria-valuemin={0} aria-valuemax={4}>
        {[0, 1, 2, 3].map((segmentIndex) => {
          const isFilled = segmentIndex < score;
          return (
            <div
              key={segmentIndex}
              className="h-1.5 overflow-hidden rounded-full bg-[var(--muted)]"
            >
              <span
                className="strength-bar-fill block h-full w-full rounded-full"
                style={{
                  transform: `scaleX(${isFilled ? 1 : 0})`,
                  backgroundColor: isFilled ? barColor : 'transparent',
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex min-h-[1rem] items-center justify-between text-[11px]">
        <span className="text-[var(--muted-foreground)]">
          {score > 0 ? 'Password strength' : 'Use 6+ chars, 10+ chars, a digit & symbol'}
        </span>
        {label && <span className={cn('font-medium', toneClass)}>{label}</span>}
      </div>
    </div>
  );
}
