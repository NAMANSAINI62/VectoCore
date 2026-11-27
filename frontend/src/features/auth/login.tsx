'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { authService } from './service';
import { useAuth } from './provider';
import { AuthDivider, GoogleSignInButton, PasswordVisibilityButton } from './AuthFormParts';
import { FloatingLabelInput } from '@/components/ui/FloatingLabelInput';
import { PasswordStrengthMeter } from '@/components/ui/PasswordStrengthMeter';
import { PinCodeInput } from '@/components/ui/PinCodeInput';
import { AlertCircle, CheckCircle2, KeyRound, Layers, LoaderCircle, Mail, MailCheck } from 'lucide-react';

type AuthMode = 'otp' | 'password' | 'reset';

interface OtpSentBannerProps {
  label: string;
  email: string;
  disabled: boolean;
  onChangeEmail: () => void;
}

function OtpSentBanner({ label, email, disabled, onChangeEmail }: OtpSentBannerProps) {
  return (
    <div
      className="flex items-center justify-between gap-3 rounded-xl border px-3.5 py-2.5"
      style={{
        backgroundColor: 'var(--hit-bg)',
        borderColor: 'var(--border)',
        color: 'var(--hit-text)',
      }}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <MailCheck className="h-4 w-4 shrink-0" />
        <div className="min-w-0">
          <p className="text-[11px] opacity-85">{label}</p>
          <p className="truncate text-xs font-medium">{email}</p>
        </div>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={onChangeEmail}
        className="shrink-0 text-[11px] font-medium underline-offset-2 hover:underline"
      >
        Change
      </button>
    </div>
  );
}

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refreshUser } = useAuth();

  const [mode, setMode] = useState<AuthMode>('otp');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [otpSent, setOtpSent] = useState(false);
  const [resetOtpSent, setResetOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [resendCooldown, setResendCooldown] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [googleRedirecting, setGoogleRedirecting] = useState(false);

  const submittingRef = useRef(false);

  useEffect(() => {
    const oauthErr = searchParams.get('error');
    if (oauthErr) {
      setError(oauthErr);
    }
  }, [searchParams]);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const id = window.setInterval(() => {
      setResendCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [resendCooldown]);

  const handleGoogleSignIn = () => {
    if (loading || googleRedirecting) return;
    setError(null);
    setNotice(null);
    setGoogleRedirecting(true);
    window.location.href = '/api/v1/auth/google/login';
  };

  const handleRequestOtp = async (event?: React.FormEvent) => {
    if (event) event.preventDefault();
    if (submittingRef.current) return;
    submittingRef.current = true;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      await authService.requestEmailOtp(email);
      setOtpCode('');
      setOtpSent(true);
      setResendCooldown(30);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not send verification code.');
    } finally {
      submittingRef.current = false;
      setLoading(false);
    }
  };

  const handleRequestResetOtp = async (event?: React.FormEvent) => {
    if (event) event.preventDefault();
    if (submittingRef.current) return;
    submittingRef.current = true;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      await authService.requestPasswordResetOtp(email);
      setOtpCode('');
      setResetOtpSent(true);
      setResendCooldown(30);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not send reset code.');
    } finally {
      submittingRef.current = false;
      setLoading(false);
    }
  };

  const verifyOtpCode = async (codeToVerify: string) => {
    if (submittingRef.current || codeToVerify.length !== 6) return;
    submittingRef.current = true;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      await authService.verifyEmailOtp(email, codeToVerify);
      const user = await refreshUser();
      if (!user) {
        setError('Sign-in could not be confirmed. Please try again.');
        return;
      }
      router.replace('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid or expired verification code.');
    } finally {
      submittingRef.current = false;
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (event: React.FormEvent) => {
    event.preventDefault();
    await verifyOtpCode(otpCode);
  };

  const handleResetPasswordSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submittingRef.current || otpCode.length !== 6) return;
    submittingRef.current = true;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const res = await authService.resetPasswordWithOtp(email, otpCode, newPassword);
      setResetOtpSent(false);
      setOtpCode('');
      setNewPassword('');
      setPassword('');
      setMode('password');
      setNotice(res.message);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not reset password.');
    } finally {
      submittingRef.current = false;
      setLoading(false);
    }
  };

  const handlePasswordSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submittingRef.current) return;
    submittingRef.current = true;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      await authService.login({ email, password });
      const user = await refreshUser();
      if (!user) {
        setError('Sign-in could not be confirmed. Please try again.');
        return;
      }
      router.replace('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed. Please check your credentials.');
    } finally {
      submittingRef.current = false;
      setLoading(false);
    }
  };

  const renderOtpBoxes = () => (
    <PinCodeInput
      length={6}
      value={otpCode}
      disabled={loading}
      autoFocus={otpSent || resetOtpSent}
      idPrefix="otp-digit"
      ariaLabelPrefix="Verification code digit"
      className="gap-1.5 sm:gap-2"
      onChange={setOtpCode}
      onComplete={(completedCode) => {
        if (mode === 'otp') {
          void verifyOtpCode(completedCode);
        }
      }}
    />
  );

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
          <h1 className="text-xl font-medium tracking-tight text-[var(--foreground)]">
            {mode === 'reset' ? 'Reset Password' : 'Sign In'}
          </h1>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">Continue with Google</p>
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

          {notice && (
            <div
              className="flex items-start gap-2 rounded-xl border px-3 py-2.5 text-xs"
              style={{
                backgroundColor: 'var(--hit-bg)',
                borderColor: 'var(--border)',
                color: 'var(--hit-text)',
              }}
            >
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{notice}</span>
            </div>
          )}

          {/* Continue with Google (OAuth 2.0) */}
          <GoogleSignInButton
            onClick={handleGoogleSignIn}
            disabled={loading || googleRedirecting}
            redirecting={googleRedirecting}
          />

          <AuthDivider />

          {/* Mode Switcher: Email OTP vs Password */}
          <div className="grid grid-cols-2 gap-1 rounded-xl border border-[var(--border)] bg-[var(--background)] p-1">
            <button
              type="button"
              onClick={() => {
                setMode('otp');
                setError(null);
                setNotice(null);
              }}
              className={`flex h-9 items-center justify-center gap-1.5 rounded-lg text-xs font-medium transition-colors ${
                mode === 'otp'
                  ? 'bg-[var(--card)] text-[var(--foreground)] shadow-xs'
                  : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
              }`}
            >
              <Mail className="h-3.5 w-3.5" />
              <span>Email OTP</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('password');
                setError(null);
                setNotice(null);
              }}
              className={`flex h-9 items-center justify-center gap-1.5 rounded-lg text-xs font-medium transition-colors ${
                mode === 'password' || mode === 'reset'
                  ? 'bg-[var(--card)] text-[var(--foreground)] shadow-xs'
                  : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
              }`}
            >
              <KeyRound className="h-3.5 w-3.5" />
              <span>Password</span>
            </button>
          </div>

          {mode === 'otp' ? (
            !otpSent ? (
              <form onSubmit={handleRequestOtp} className="space-y-4">
                <FloatingLabelInput
                  id="otp-email"
                  type="email"
                  label="Email Address"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl px-4 text-xs font-medium transition-opacity hover:opacity-90 disabled:opacity-60"
                  style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }}
                >
                  {loading && <LoaderCircle className="h-4 w-4 animate-spin" />}
                  <span>{loading ? 'Sending code...' : 'Continue with Email'}</span>
                </button>
              </form>
            ) : (
              <form onSubmit={handleVerifyOtp} className="space-y-4">
                <OtpSentBanner
                  label="Verification code sent"
                  email={email}
                  disabled={loading}
                  onChangeEmail={() => {
                    setOtpSent(false);
                    setOtpCode('');
                    setError(null);
                  }}
                />

                <div className="space-y-2">
                  <label htmlFor="otp-digit-0" className="block text-xs font-medium text-[var(--foreground)]">
                    Verification Code
                  </label>
                  {renderOtpBoxes()}
                </div>

                <button
                  type="submit"
                  disabled={loading || otpCode.length !== 6}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl px-4 text-xs font-medium transition-opacity hover:opacity-90 disabled:opacity-60"
                  style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }}
                >
                  {loading && <LoaderCircle className="h-4 w-4 animate-spin" />}
                  <span>{loading ? 'Verifying & Signing in...' : 'Verify & Sign In'}</span>
                </button>

                <div className="flex items-center justify-end text-xs text-[var(--muted-foreground)]">
                  <button
                    type="button"
                    disabled={resendCooldown > 0 || loading}
                    onClick={() => handleRequestOtp()}
                    className="font-medium text-[var(--foreground)] hover:underline disabled:opacity-50"
                  >
                    {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend code'}
                  </button>
                </div>
              </form>
            )
          ) : mode === 'reset' ? (
            !resetOtpSent ? (
              <form onSubmit={handleRequestResetOtp} className="space-y-4">
                <FloatingLabelInput
                  id="reset-email"
                  type="email"
                  label="Email Address"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl px-4 text-xs font-medium transition-opacity hover:opacity-90 disabled:opacity-60"
                  style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }}
                >
                  {loading && <LoaderCircle className="h-4 w-4 animate-spin" />}
                  <span>{loading ? 'Sending reset code...' : 'Send Reset Code'}</span>
                </button>
                <div className="text-center text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      setMode('password');
                      setError(null);
                    }}
                    className="font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:underline"
                  >
                    Back to Sign In
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleResetPasswordSubmit} className="space-y-4">
                <OtpSentBanner
                  label="Reset code sent"
                  email={email}
                  disabled={loading}
                  onChangeEmail={() => {
                    setResetOtpSent(false);
                    setOtpCode('');
                    setError(null);
                  }}
                />

                <div className="space-y-2">
                  <label htmlFor="otp-digit-0" className="block text-xs font-medium text-[var(--foreground)]">
                    Verification Code
                  </label>
                  {renderOtpBoxes()}
                </div>

                <div className="space-y-2">
                  <FloatingLabelInput
                    id="new-password"
                    type={showPassword ? 'text' : 'password'}
                    label="New Password (min 8 characters)"
                    autoComplete="new-password"
                    minLength={8}
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    required
                    rightSlot={
                      <PasswordVisibilityButton
                        visible={showPassword}
                        onToggle={() => setShowPassword((prev) => !prev)}
                      />
                    }
                  />
                  <PasswordStrengthMeter value={newPassword} />
                </div>

                <button
                  type="submit"
                  disabled={loading || otpCode.length !== 6 || newPassword.length < 8}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl px-4 text-xs font-medium transition-opacity hover:opacity-90 disabled:opacity-60"
                  style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }}
                >
                  {loading && <LoaderCircle className="h-4 w-4 animate-spin" />}
                  <span>{loading ? 'Resetting password...' : 'Reset Password'}</span>
                </button>

                <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
                  <button
                    type="button"
                    onClick={() => {
                      setMode('password');
                      setResetOtpSent(false);
                      setError(null);
                    }}
                    className="hover:text-[var(--foreground)] hover:underline"
                  >
                    Back to Sign In
                  </button>
                  <button
                    type="button"
                    disabled={resendCooldown > 0 || loading}
                    onClick={() => handleRequestResetOtp()}
                    className="font-medium text-[var(--foreground)] hover:underline disabled:opacity-50"
                  >
                    {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : 'Resend code'}
                  </button>
                </div>
              </form>
            )
          ) : (
            <form onSubmit={handlePasswordSubmit} className="space-y-4">
              <FloatingLabelInput
                id="email"
                type="email"
                label="Email Address"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />

              <div className="space-y-1.5">
                <FloatingLabelInput
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  label="Password"
                  autoComplete="current-password"
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
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => {
                      setMode('reset');
                      setResetOtpSent(false);
                      setOtpCode('');
                      setError(null);
                      setNotice(null);
                    }}
                    className="text-xs font-medium text-[var(--accent)] hover:underline"
                  >
                    Forgot password?
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="flex h-11 w-full items-center justify-center gap-2 rounded-xl px-4 text-xs font-medium transition-opacity hover:opacity-90 disabled:opacity-60"
                style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }}
              >
                {loading && <LoaderCircle className="h-4 w-4 animate-spin" />}
                <span>{loading ? 'Signing in...' : 'Sign In'}</span>
              </button>
            </form>
          )}

          <div className="pt-1 text-center text-xs text-[var(--muted-foreground)]">
            Don&apos;t have an account?{' '}
            <Link href="/register" className="font-medium text-[var(--foreground)] hover:underline">
              Create one
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
