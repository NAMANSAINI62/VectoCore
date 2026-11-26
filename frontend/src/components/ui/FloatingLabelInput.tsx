'use client';

import React, { useId } from 'react';
import { cn } from '@/lib/utils';

export interface FloatingLabelInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  rightSlot?: React.ReactNode;
  containerClassName?: string;
}

/**
 * Pure CSS floating-label text field using placeholder=" " and :placeholder-shown.
 */
export const FloatingLabelInput = React.forwardRef<HTMLInputElement, FloatingLabelInputProps>(
  ({ className, containerClassName, label, error, id, rightSlot, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id ?? generatedId;

    return (
      <div className={cn('w-full', containerClassName)}>
        <div className="floating-field">
          <input
            id={inputId}
            ref={ref}
            placeholder=" "
            className={cn(
              'floating-field__input h-12 w-full rounded-xl border border-[var(--border)] bg-[var(--background)]/60 px-3.5 text-sm text-[var(--foreground)] transition-colors focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20 disabled:opacity-50',
              rightSlot ? 'pr-10' : '',
              error ? 'border-rose-500 focus:border-rose-500 focus:ring-rose-500/20' : '',
              className
            )}
            {...props}
          />
          <label htmlFor={inputId} className="floating-field__label">
            {label}
          </label>
          {rightSlot && (
            <div className="absolute right-2.5 top-1/2 -translate-y-1/2">{rightSlot}</div>
          )}
        </div>
        {error && <p className="mt-1 text-xs text-rose-500">{error}</p>}
      </div>
    );
  }
);

FloatingLabelInput.displayName = 'FloatingLabelInput';
