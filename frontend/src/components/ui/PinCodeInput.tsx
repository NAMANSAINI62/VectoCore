'use client';

import React, { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

export interface PinCodeInputProps {
  length?: number;
  value?: string;
  onChange?: (value: string) => void;
  onComplete?: (value: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
  idPrefix?: string;
  ariaLabelPrefix?: string;
  className?: string;
}

/**
 * Single-character PIN / OTP box input (default 4 boxes) with spring pop on fill,
 * accent border for filled boxes, auto-advance, and Backspace-to-previous navigation.
 */
export function PinCodeInput({
  length = 4,
  value,
  onChange,
  onComplete,
  disabled = false,
  autoFocus = false,
  idPrefix = 'pin-digit',
  ariaLabelPrefix = 'PIN digit',
  className,
}: PinCodeInputProps) {
  const [internalDigits, setInternalDigits] = useState<string[]>(() => Array(length).fill(''));
  const [popping, setPopping] = useState<boolean[]>(() => Array(length).fill(false));
  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);

  const digits: string[] =
    value !== undefined
      ? Array.from({ length }, (_, idx) => value[idx] ?? '')
      : internalDigits;

  useEffect(() => {
    if (autoFocus) {
      inputRefs.current[0]?.focus();
    }
  }, [autoFocus]);

  const triggerPop = (indices: number[]) => {
    setPopping((prev) => {
      const next = [...prev];
      indices.forEach((idx) => {
        next[idx] = false;
      });
      return next;
    });
    window.requestAnimationFrame(() => {
      setPopping((prev) => {
        const next = [...prev];
        indices.forEach((idx) => {
          next[idx] = true;
        });
        return next;
      });
    });
  };

  const clearPop = (index: number) => {
    setPopping((prev) => {
      if (!prev[index]) return prev;
      const next = [...prev];
      next[index] = false;
      return next;
    });
  };

  const commitDigits = (next: string[]) => {
    if (value === undefined) {
      setInternalDigits(next);
    }
    const joined = next.join('');
    onChange?.(joined);
    if (next.every((d) => d.length === 1)) {
      onComplete?.(joined);
    }
  };

  const handleChange = (index: number, rawValue: string) => {
    const cleaned = rawValue.replace(/\D/g, '');
    if (!cleaned) {
      const next = [...digits];
      next[index] = '';
      commitDigits(next);
      return;
    }

    if (cleaned.length > 1) {
      const next = [...digits];
      const chars = cleaned.slice(0, length - index).split('');
      const popped: number[] = [];
      chars.forEach((ch, offset) => {
        const targetIdx = index + offset;
        if (targetIdx < length) {
          next[targetIdx] = ch;
          popped.push(targetIdx);
        }
      });
      triggerPop(popped);
      commitDigits(next);
      const nextFocus = Math.min(index + chars.length, length - 1);
      inputRefs.current[nextFocus]?.focus();
      return;
    }

    const next = [...digits];
    next[index] = cleaned;
    triggerPop([index]);
    commitDigits(next);

    if (index < length - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    } else if (event.key === 'ArrowLeft' && index > 0) {
      inputRefs.current[index - 1]?.focus();
    } else if (event.key === 'ArrowRight' && index < length - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    const pasted = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, length);
    if (!pasted) return;
    event.preventDefault();
    const next = Array(length).fill('');
    const popped: number[] = [];
    pasted.split('').forEach((ch, idx) => {
      next[idx] = ch;
      popped.push(idx);
    });
    triggerPop(popped);
    commitDigits(next);
    inputRefs.current[Math.min(pasted.length, length - 1)]?.focus();
  };

  return (
    <div
      className={cn('grid gap-2', className)}
      style={{ gridTemplateColumns: `repeat(${length}, minmax(0, 1fr))` }}
    >
      {digits.map((digit, index) => {
        const isFilled = digit.length === 1;
        return (
          <input
            key={index}
            id={`${idPrefix}-${index}`}
            ref={(el) => {
              inputRefs.current[index] = el;
            }}
            type="text"
            inputMode="numeric"
            autoComplete={index === 0 ? 'one-time-code' : 'off'}
            maxLength={length}
            value={digit}
            disabled={disabled}
            onChange={(event) => handleChange(index, event.target.value)}
            onKeyDown={(event) => handleKeyDown(index, event)}
            onPaste={handlePaste}
            onAnimationEnd={() => clearPop(index)}
            aria-label={`${ariaLabelPrefix} ${index + 1}`}
            className={cn(
              'h-12 w-full rounded-xl border bg-[var(--background)]/70 text-center text-lg font-medium tabular-nums text-[var(--foreground)] transition-colors focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30 disabled:opacity-60',
              isFilled ? 'border-[var(--accent)]' : 'border-[var(--border)]',
              popping[index] ? 'pin-box-pop' : ''
            )}
          />
        );
      })}
    </div>
  );
}
