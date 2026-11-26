'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authService } from './service';
import { FloatingLabelInput } from '@/components/ui/FloatingLabelInput';
import { PasswordStrengthMeter } from '@/components/ui/PasswordStrengthMeter';
import { AlertCircle, CheckCircle2, Eye, EyeOff, Layers, LoaderCircle } from 'lucide-react';

export function RegisterForm() {
  const router = useRouter();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleRedirecting, setGoogleRedirecting] = useState(false);

  const handleGoogleSignIn = () => {
    if (loading || googleRedirecting) return;
    setError(null);
    setGoogleRedirecting(true);
    window.location.href = '/api/v1/auth/google/login';
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authService.register({ full_name: fullName, email, password });
      setSuccess(true);
      setTimeout(() => router.push('/login'), 1500);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-[var(--background)] px-4 py-8 text-[var(--foreground)]">
      <div className="w-full max-w-[420px] rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm sm:p-7">
        <div className="text-center">
          <div
            className="mx-auto mb-3.5 flex h-10 w-10 items-center justify-center rounded-xl"
            style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }}
          >
            <Layers className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <h1 className="text-xl font-medium tracking-tight text-[var(--foreground)]">Create Account</h1>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">Continue with Google or create a password</p>
        </div>

        <div className="mt-5 space-y-4">
          {error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-xl border px-3 py-2.5 text-xs"
              style={{
                backgroundColor: 'var(--miss-bg)',
                borderColor: 'var(--border)',
                color: 'var(--miss-text)',
              }}
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div
              className="flex items-center gap-2 rounded-xl border px-3 py-2.5 text-xs"
              style={{
                backgroundColor: 'var(--hit-bg)',
                borderColor: 'var(--border)',
                color: 'var(--hit-text)',
              }}
            >
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>Account created. Redirecting to sign in...</span>
            </div>
          )}

          <button
            type="button"
            onClick={handleGoogleSignIn}
            disabled={loading || success || googleRedirecting}
            className="flex h-11 w-full items-center justify-center gap-2.5 rounded-xl border border-[var(--border)] bg-[var(--background)]/70 px-4 text-xs font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--muted)] disabled:opacity-60"
          >
            {googleRedirecting ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  fill="#4285F4"
                  d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17Z"
                />
                <path
                  fill="#34A853"
                  d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.11-6.72-4.96H1.29v3.14C3.26 21.3 7.31 24 12 24Z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.28 14.24c-.24-.72-.38-1.49-.38-2.24s.14-1.52.38-2.24V6.62H1.29C.47 8.24 0 10.06 0 12s.47 3.76 1.29 5.38l3.99-3.14Z"
                />
                <path
                  fill="#EA4335"
                  d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.99 3.14c.95-2.85 3.6-4.96 6.72-4.96Z"
                />
              </svg>
            )}
            <span>{googleRedirecting ? 'Redirecting to Google...' : 'Continue with Google'}</span>
          </button>

          <div className="relative flex items-center py-0.5">
            <div className="flex-grow border-t border-[var(--border)]" />
            <span className="mx-3 shrink-0 text-[11px] uppercase tracking-wider text-[var(--muted-foreground)]">
              or
            </span>
            <div className="flex-grow border-t border-[var(--border)]" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <FloatingLabelInput
              id="fullName"
              type="text"
              label="Full Name"
              autoComplete="name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
            />

            <FloatingLabelInput
              id="email"
              type="email"
              label="Email Address"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />

            <div className="space-y-2">
              <FloatingLabelInput
                id="password"
                type={showPassword ? 'text' : 'password'}
                label="Password (min 8 characters)"
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
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
            </div>

            <button
              type="submit"
              disabled={loading || success}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-xl px-4 text-xs font-medium transition-opacity hover:opacity-90 disabled:opacity-60"
              style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }}
            >
              {loading && <LoaderCircle className="h-4 w-4 animate-spin" />}
              <span>{loading ? 'Creating account...' : 'Create Account'}</span>
            </button>

            <div className="pt-1 text-center text-xs text-[var(--muted-foreground)]">
              Already have an account?{' '}
              <Link href="/login" className="font-medium text-[var(--foreground)] hover:underline">
                Sign In
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
