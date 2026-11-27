'use client';

import React, { useEffect, useState } from 'react';
import {
  Check,
  Cpu,
  Database,
  KeyRound,
  LoaderCircle,
  LogOut,
  Mail,
  Palette,
  Shield,
  SlidersHorizontal,
  Trash2,
  UserRound,
} from 'lucide-react';
import { getSavedDefaultModel, saveDefaultModel } from '@/lib/preferences';
import { useAuth } from '@/features/auth/provider';
import { authService } from '@/features/auth/service';
import type { AuthMethods } from '@/features/auth/types';
import { formatProviderLabel } from '@/features/chatbot/ModelSelector';
import { THEME_OPTIONS, useTheme } from '@/components/ThemeProvider';
import {
  useClearCacheEntriesMutation,
  useGetCacheSettingsQuery,
  useGetModelsQuery,
  useUpdateCacheSettingsMutation,
} from '@/store/cacheApi';

const TTL_PRESETS = [
  { id: '1d', label: '1 Day', hours: 24, hint: '24 hours' },
  { id: '2d', label: '2 Days (Default)', hours: 48, hint: '48 hours' },
  { id: 'custom', label: 'Custom', hours: null, hint: '1–48 hours' },
] as const;

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const { theme, setTheme } = useTheme();

  // 1. Profile state
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [authMethods, setAuthMethods] = useState<AuthMethods | null>(null);

  useEffect(() => {
    if (user?.full_name) setFullName(user.full_name);
  }, [user?.full_name]);

  useEffect(() => {
    void authService.getAuthMethods().then(setAuthMethods).catch(() => {});
  }, []);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = fullName.trim();
    if (cleaned.length < 2) {
      setProfileMsg('Name must be at least 2 characters.');
      return;
    }
    setProfileSaving(true);
    setProfileMsg(null);
    try {
      await authService.updateProfile(cleaned);
      await refreshUser();
      setProfileMsg('Profile updated.');
    } catch (err) {
      setProfileMsg(err instanceof Error ? err.message : 'Failed to update profile.');
    } finally {
      setProfileSaving(false);
    }
  };

  // 2. Security state (Change password, OTP reset, Logout all sessions)
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [pwSaving, setPwSaving] = useState(false);
  const [pwMsg, setPwMsg] = useState<string | null>(null);

  const [otpRequested, setOtpRequested] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [otpNewPassword, setOtpNewPassword] = useState('');
  const [otpBusy, setOtpBusy] = useState(false);
  const [otpMsg, setOtpMsg] = useState<string | null>(null);

  const [confirmLogoutAll, setConfirmLogoutAll] = useState(false);
  const [logoutAllBusy, setLogoutAllBusy] = useState(false);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPassword || newPassword.length < 8) {
      setPwMsg('New password must be at least 8 characters.');
      return;
    }
    setPwSaving(true);
    setPwMsg(null);
    try {
      const res = await authService.changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setPwMsg(res.message);
    } catch (err) {
      setPwMsg(err instanceof Error ? err.message : 'Failed to change password.');
    } finally {
      setPwSaving(false);
    }
  };

  const handleRequestResetOtp = async () => {
    if (!user?.email) return;
    setOtpBusy(true);
    setOtpMsg(null);
    try {
      const res = await authService.requestPasswordResetOtp(user.email);
      setOtpRequested(true);
      setOtpMsg(res.message || 'Verification code sent to your email.');
    } catch (err) {
      setOtpMsg(err instanceof Error ? err.message : 'Could not send reset OTP.');
    } finally {
      setOtpBusy(false);
    }
  };

  const handleConfirmResetOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user?.email || otpCode.length !== 6 || otpNewPassword.length < 8) {
      setOtpMsg('Enter the 6-digit code and an 8+ character password.');
      return;
    }
    setOtpBusy(true);
    setOtpMsg(null);
    try {
      const res = await authService.resetPasswordWithOtp(user.email, otpCode, otpNewPassword);
      setOtpCode('');
      setOtpNewPassword('');
      setOtpRequested(false);
      setOtpMsg(res.message || 'Password reset via OTP complete.');
    } catch (err) {
      setOtpMsg(err instanceof Error ? err.message : 'Invalid OTP or password.');
    } finally {
      setOtpBusy(false);
    }
  };

  const handleLogoutAllSessions = async () => {
    setLogoutAllBusy(true);
    try {
      await authService.logoutAll();
    } finally {
      window.location.href = '/login';
    }
  };

  // 3. Semantic Cache Settings (Similarity threshold 0.70..0.99, TTL 1..48h default 48h, Clear My Cache)
  const { data: cacheSettings } = useGetCacheSettingsQuery();
  const [updateCacheSettings, { isLoading: savingCacheSettings }] = useUpdateCacheSettingsMutation();
  const [clearCacheEntries, { isLoading: clearingCache }] = useClearCacheEntriesMutation();

  const [similarity, setSimilarity] = useState(0.82);
  const [ttlHours, setTtlHours] = useState(48);
  const [ttlMode, setTtlMode] = useState<'1d' | '2d' | 'custom'>('2d');
  const [cacheMsg, setCacheMsg] = useState<string | null>(null);
  const [confirmClearCache, setConfirmClearCache] = useState(false);

  useEffect(() => {
    if (!cacheSettings) return;
    const clampedSim = Math.min(0.99, Math.max(0.7, cacheSettings.similarity_threshold ?? 0.82));
    setSimilarity(clampedSim);
    const clampedTtl = Math.min(48, Math.max(1, cacheSettings.default_ttl_hours ?? 48));
    setTtlHours(clampedTtl);
    if (clampedTtl === 24) setTtlMode('1d');
    else if (clampedTtl === 48) setTtlMode('2d');
    else setTtlMode('custom');
  }, [cacheSettings]);

  const handleSelectTtlPreset = (presetId: '1d' | '2d' | 'custom', hours: number | null) => {
    setTtlMode(presetId);
    if (hours !== null) setTtlHours(hours);
  };

  const handleSaveCacheSettings = async () => {
    setCacheMsg(null);
    try {
      await updateCacheSettings({
        similarity_threshold: Number(similarity.toFixed(2)),
        default_ttl_hours: ttlHours,
      }).unwrap();
      setCacheMsg(`Saved: similarity ${similarity.toFixed(2)}, TTL ${ttlHours}h.`);
    } catch {
      setCacheMsg('Failed to update cache settings.');
    }
  };

  const handleClearMyCache = async () => {
    setCacheMsg(null);
    try {
      const res = await clearCacheEntries().unwrap();
      setConfirmClearCache(false);
      setCacheMsg(`Cleared ${res.deleted} cached entry(s).`);
    } catch {
      setCacheMsg('Failed to clear cache.');
    }
  };

  // 4. Default Startup Model
  const { data: models = [] } = useGetModelsQuery();
  const [selectedModelKey, setSelectedModelKey] = useState<string>('');
  const [modelMsg, setModelMsg] = useState<string | null>(null);

  useEffect(() => {
    const saved = getSavedDefaultModel();
    if (saved) {
      setSelectedModelKey(`${saved.provider}::${saved.modelId}`);
    } else if (models.length > 0) {
      const first = models[0];
      setSelectedModelKey(`${first.provider}::${first.id}`);
    }
  }, [models]);

  const handleSaveDefaultModel = () => {
    const [provider, modelId] = selectedModelKey.split('::');
    if (!provider || !modelId) return;
    saveDefaultModel(provider, modelId);
    const match = models.find((m) => m.provider === provider && m.id === modelId);
    setModelMsg(`Default startup model saved: ${match?.name ?? modelId}.`);
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--foreground)] flex items-center gap-2">
          <SlidersHorizontal className="h-5 w-5 text-[var(--accent)]" />
          Workspace &amp; Account Settings
        </h1>
        <p className="text-xs text-[var(--muted-foreground)] mt-1">
          Manage your profile, account security, semantic cache controls, startup model, and light themes.
        </p>
      </div>

      {/* 1. Profile & Account */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-4">
        <div className="flex items-center gap-2">
          <UserRound className="h-4 w-4 text-[var(--accent)]" />
          <h2 className="text-sm font-semibold text-[var(--foreground)]">Profile &amp; Account</h2>
        </div>

        <form onSubmit={handleSaveProfile} className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
          <label className="block text-xs font-medium text-[var(--muted-foreground)]">
            Full Name
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              minLength={2}
              maxLength={150}
              className="mt-1.5 w-full rounded-xl border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            />
          </label>

          <label className="block text-xs font-medium text-[var(--muted-foreground)]">
            Account Email (Read-only)
            <input
              type="email"
              value={user?.email ?? ''}
              readOnly
              className="mt-1.5 w-full rounded-xl border border-[var(--border)] bg-[var(--muted)]/60 px-3 py-2 text-xs text-[var(--muted-foreground)] cursor-not-allowed"
            />
          </label>

          <div className="md:col-span-2 flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
              <span>Sign-in methods:</span>
              <span className="rounded-full border border-[var(--border)] bg-[var(--background)] px-2.5 py-0.5 font-medium text-[var(--foreground)]">
                Password
              </span>
              {authMethods?.email_otp_enabled && (
                <span className="rounded-full border border-[var(--border)] bg-[var(--background)] px-2.5 py-0.5 font-medium text-[var(--foreground)]">
                  Email OTP
                </span>
              )}
              {authMethods?.google_enabled && (
                <span className="rounded-full border border-[var(--border)] bg-[var(--background)] px-2.5 py-0.5 font-medium text-[var(--foreground)]">
                  Google OAuth
                </span>
              )}
            </div>

            <div className="flex items-center gap-3">
              {profileMsg && <span className="text-xs text-[var(--accent)] font-medium">{profileMsg}</span>}
              <button
                type="submit"
                disabled={profileSaving}
                className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--accent)] px-4 py-2 text-xs font-semibold text-[var(--accent-foreground)] transition hover:opacity-90 disabled:opacity-50 cursor-pointer"
              >
                {profileSaving && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}
                Save Profile
              </button>
            </div>
          </div>
        </form>
      </section>

      {/* 2. Security */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-5">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-[var(--accent)]" />
          <h2 className="text-sm font-semibold text-[var(--foreground)]">Account Security</h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Change Password */}
          <form onSubmit={handleChangePassword} className="rounded-xl border border-[var(--border)] bg-[var(--background)]/60 p-4 space-y-3">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--foreground)]">
              <KeyRound className="h-3.5 w-3.5 text-[var(--accent)]" />
              Change Password
            </div>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Current password"
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            />
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="New password (min 8 characters)"
              minLength={8}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            />
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] text-[var(--muted-foreground)] truncate">{pwMsg}</span>
              <button
                type="submit"
                disabled={pwSaving}
                className="rounded-lg bg-[var(--accent)] px-3.5 py-1.5 text-xs font-semibold text-[var(--accent-foreground)] transition hover:opacity-90 disabled:opacity-50 cursor-pointer shrink-0"
              >
                {pwSaving ? 'Updating…' : 'Update Password'}
              </button>
            </div>
          </form>

          {/* Reset via Email OTP */}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--background)]/60 p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--foreground)]">
                <Mail className="h-3.5 w-3.5 text-[var(--accent)]" />
                Reset Password via Email OTP
              </div>
              <button
                type="button"
                onClick={() => void handleRequestResetOtp()}
                disabled={otpBusy || !user?.email}
                className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-1 text-[11px] font-semibold text-[var(--foreground)] hover:bg-[var(--muted)] disabled:opacity-50 cursor-pointer"
              >
                {otpRequested ? 'Resend OTP' : 'Send Reset OTP'}
              </button>
            </div>

            {otpRequested ? (
              <form onSubmit={handleConfirmResetOtp} className="space-y-2.5">
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="6-digit OTP code"
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] tracking-widest focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
                <input
                  type="password"
                  value={otpNewPassword}
                  onChange={(e) => setOtpNewPassword(e.target.value)}
                  placeholder="New password (min 8 characters)"
                  minLength={8}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] text-[var(--muted-foreground)] truncate">{otpMsg}</span>
                  <button
                    type="submit"
                    disabled={otpBusy}
                    className="rounded-lg bg-[var(--accent)] px-3.5 py-1.5 text-xs font-semibold text-[var(--accent-foreground)] transition hover:opacity-90 disabled:opacity-50 cursor-pointer shrink-0"
                  >
                    Confirm Reset
                  </button>
                </div>
              </form>
            ) : (
              <p className="text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                {otpMsg ||
                  `Send a 6-digit verification code to ${user?.email ?? 'your email'} to set or reset your password without entering the old one.`}
              </p>
            )}
          </div>
        </div>

        {/* Sign out of all sessions */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/25 bg-rose-500/[0.04] px-4 py-3">
          <div>
            <p className="text-xs font-semibold text-[var(--foreground)]">Active Sessions</p>
            <p className="text-[11px] text-[var(--muted-foreground)]">
              Revoke all refresh tokens across every browser and device immediately.
            </p>
          </div>
          {!confirmLogoutAll ? (
            <button
              type="button"
              onClick={() => setConfirmLogoutAll(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-[var(--card)] px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-500/10 cursor-pointer"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign out of all sessions
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setConfirmLogoutAll(false)}
                className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs font-medium text-[var(--muted-foreground)] cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleLogoutAllSessions()}
                disabled={logoutAllBusy}
                className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50 cursor-pointer"
              >
                {logoutAllBusy ? 'Signing out…' : 'Confirm Sign Out All'}
              </button>
            </div>
          )}
        </div>
      </section>

      {/* 3. Semantic Cache Settings */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-5">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-[var(--accent)]" />
          <h2 className="text-sm font-semibold text-[var(--foreground)]">Semantic Cache Settings</h2>
        </div>

        {/* Similarity Slider */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-[var(--foreground)]">Similarity Threshold</span>
            <span className="font-mono font-semibold text-[var(--accent)]">{similarity.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0.7}
            max={0.99}
            step={0.01}
            value={similarity}
            onChange={(e) => setSimilarity(parseFloat(e.target.value))}
            className="w-full accent-[var(--accent)] cursor-pointer"
          />
          <div className="flex justify-between text-[10.5px] text-[var(--muted-foreground)]">
            <span>0.70 (More hits, relaxed)</span>
            <span>0.82 (Recommended)</span>
            <span>0.99 (Strict match)</span>
          </div>
        </div>

        {/* Default Cache TTL: 1–48 hours (1d, 2d=48h default, Custom) */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-[var(--foreground)]">Default Cache TTL (1 – 48 hours)</span>
            <span className="font-mono font-semibold text-[var(--accent)]">{ttlHours} hours</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            {TTL_PRESETS.map((preset) => {
              const active = ttlMode === preset.id;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handleSelectTtlPreset(preset.id, preset.hours)}
                  className={`rounded-xl border p-2.5 text-left transition cursor-pointer ${
                    active
                      ? 'border-[var(--accent)] bg-[var(--accent)]/12'
                      : 'border-[var(--border)] bg-[var(--background)]/60 hover:bg-[var(--muted)]'
                  }`}
                >
                  <div className="text-xs font-semibold text-[var(--foreground)]">{preset.label}</div>
                  <div className="text-[10.5px] text-[var(--muted-foreground)] mt-0.5">{preset.hint}</div>
                </button>
              );
            })}
          </div>

          <input
            type="range"
            min={1}
            max={48}
            step={1}
            value={ttlHours}
            onChange={(e) => {
              const h = parseInt(e.target.value, 10);
              setTtlHours(h);
              if (h === 24) setTtlMode('1d');
              else if (h === 48) setTtlMode('2d');
              else setTtlMode('custom');
            }}
            className="w-full accent-[var(--accent)] cursor-pointer"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-[var(--border)]">
          {/* Clear My Cache with Confirmation */}
          <div>
            {!confirmClearCache ? (
              <button
                type="button"
                onClick={() => setConfirmClearCache(true)}
                className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/35 bg-rose-500/[0.06] px-3.5 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-500/15 cursor-pointer"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear My Cache
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-rose-700">Delete all your cache entries?</span>
                <button
                  type="button"
                  onClick={() => setConfirmClearCache(false)}
                  className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-xs text-[var(--muted-foreground)] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleClearMyCache()}
                  disabled={clearingCache}
                  className="rounded-lg bg-rose-600 px-3 py-1 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50 cursor-pointer"
                >
                  {clearingCache ? 'Clearing…' : 'Confirm Clear'}
                </button>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            {cacheMsg && <span className="text-xs font-medium text-[var(--accent)]">{cacheMsg}</span>}
            <button
              type="button"
              onClick={() => void handleSaveCacheSettings()}
              disabled={savingCacheSettings}
              className="rounded-xl bg-[var(--accent)] px-4 py-2 text-xs font-semibold text-[var(--accent-foreground)] transition hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              {savingCacheSettings ? 'Saving…' : 'Save Cache Settings'}
            </button>
          </div>
        </div>
      </section>

      {/* 4. Default Startup Model */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-5">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-[var(--accent)]" />
          <h2 className="text-sm font-semibold text-[var(--foreground)]">Playground Startup Model</h2>
        </div>

        {/* Default Startup Model */}
        <div className="rounded-xl border border-[var(--border)] bg-[var(--background)]/60 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-[var(--foreground)]">Default Startup Model ({models.length} configured)</p>
              <p className="text-[11px] text-[var(--muted-foreground)]">Selected automatically whenever you open AI Playground.</p>
            </div>
            <div className="flex items-center gap-2">
              {modelMsg && <span className="text-xs font-medium text-[var(--accent)]">{modelMsg}</span>}
              <button
                type="button"
                onClick={handleSaveDefaultModel}
                className="rounded-lg bg-[var(--accent)] px-3.5 py-1.5 text-xs font-semibold text-[var(--accent-foreground)] transition hover:opacity-90 cursor-pointer"
              >
                Save Model
              </button>
            </div>
          </div>

          <select
            value={selectedModelKey}
            onChange={(e) => setSelectedModelKey(e.target.value)}
            className="w-full rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs font-medium text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
          >
            {models.map((m) => (
              <option key={`${m.provider}::${m.id}`} value={`${m.provider}::${m.id}`}>
                {m.name} ({formatProviderLabel(m.provider)})
              </option>
            ))}
          </select>
        </div>
      </section>

      {/* 5. Appearance (5 Light Themes — 60-30-10 Palette) */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Palette className="h-4 w-4 text-[var(--accent)]" />
            <h2 className="text-sm font-semibold text-[var(--foreground)]">Appearance (60-30-10 Light Themes)</h2>
          </div>
          <span className="text-[11px] text-[var(--muted-foreground)]">Instant preview across workspace</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {THEME_OPTIONS.map((opt) => {
            const active = theme === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setTheme(opt.id)}
                className={`rounded-xl border p-3 text-left transition cursor-pointer ${
                  active
                    ? 'border-[var(--accent)] bg-[var(--accent)]/10 ring-1 ring-[var(--accent)]/30'
                    : 'border-[var(--border)] bg-[var(--background)]/60 hover:bg-[var(--muted)]'
                }`}
              >
                {/* 60-30-10 Swatch Bar */}
                <div className="flex h-5 w-full overflow-hidden rounded-lg border border-[var(--border)] mb-2">
                  <span className="h-full w-[60%]" style={{ backgroundColor: opt.swatch }} />
                  <span className="h-full w-[30%]" style={{ backgroundColor: opt.secondarySwatch }} />
                  <span className="h-full w-[10%]" style={{ backgroundColor: opt.accentSwatch }} />
                </div>
                <div className="flex items-center justify-between gap-1">
                  <span className="text-xs font-semibold text-[var(--foreground)] truncate">{opt.label}</span>
                  {active && <Check className="h-3.5 w-3.5 text-[var(--accent)] shrink-0" />}
                </div>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
