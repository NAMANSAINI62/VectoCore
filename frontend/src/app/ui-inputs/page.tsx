'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { FloatingLabelInput } from '@/components/ui/FloatingLabelInput';
import { PasswordStrengthMeter } from '@/components/ui/PasswordStrengthMeter';
import { PinCodeInput } from '@/components/ui/PinCodeInput';
import { Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react';

export default function UiInputsPage() {
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [pin, setPin] = useState('');

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-[var(--background)] px-4 py-10 text-[var(--foreground)]">
      <div className="w-full max-w-[460px] space-y-6 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm sm:p-7">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-xl"
              style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }}
            >
              <ShieldCheck className="h-4 w-4" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[var(--foreground)]">Interactive Auth Inputs</h1>
              <p className="text-xs text-[var(--muted-foreground)]">Floating labels, strength meter &amp; 4-digit PIN</p>
            </div>
          </div>
          <Link href="/login" className="text-xs font-medium text-[var(--accent)] hover:underline">
            Sign In
          </Link>
        </div>

        <section className="space-y-2.5">
          <h2 className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
            1. Pure CSS Floating-Label Field
          </h2>
          <FloatingLabelInput
            id="demo-floating-name"
            type="text"
            label="Workspace Name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </section>

        <section className="space-y-2.5">
          <h2 className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
            2. Password Strength Meter
          </h2>
          <FloatingLabelInput
            id="demo-password"
            type={showPassword ? 'text' : 'password'}
            label="Create Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            rightSlot={
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="rounded-md p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            }
          />
          <PasswordStrengthMeter value={password} />
        </section>

        <section className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
              <KeyRound className="h-3.5 w-3.5" />
              <span>3. 4-Digit PIN / OTP Input</span>
            </h2>
            <span className="text-xs tabular-nums text-[var(--muted-foreground)]">
              Value: {pin || '—'}
            </span>
          </div>
          <PinCodeInput length={4} value={pin} onChange={setPin} />
        </section>
      </div>
    </div>
  );
}
