'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authService } from './service';
import { AuthDivider, GoogleSignInButton, PasswordVisibilityButton } from './AuthFormParts';
import { FloatingLabelInput } from '@/components/ui/FloatingLabelInput';
import { PasswordStrengthMeter } from '@/components/ui/PasswordStrengthMeter';
import { AlertCircle, CheckCircle2, Layers, LoaderCircle } from 'lucide-react';

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

          <GoogleSignInButton
            onClick={handleGoogleSignIn}
            disabled={loading || success || googleRedirecting}
            redirecting={googleRedirecting}
          />

          <AuthDivider />

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
                  <PasswordVisibilityButton
                    visible={showPassword}
                    onToggle={() => setShowPassword((prev) => !prev)}
                  />
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
