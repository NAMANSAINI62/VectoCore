'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/react';
import {
  BarChart3,
  Check,
  Cpu,
  Database,
  FileText,
  LayoutDashboard,
  Layers,
  LogOut,
  MessageSquare,
  Palette,
  Settings,
  UserRound,
} from 'lucide-react';
import { useAuth } from '@/features/auth/provider';
import { THEME_OPTIONS, useTheme } from '@/components/ThemeProvider';
import { DateRangeFilter } from '@/components/analytics/DateRangeFilter';
import { useGetCacheStatsQuery } from '@/store/cacheApi';
import { useAppDispatch, useAppSelector } from '@/store';
import { setCustomDateRange, setDatePreset } from '@/store/dateRangeSlice';

const navigation = [
  { label: 'Overview', shortLabel: 'Overview', href: '/', icon: LayoutDashboard },
  { label: 'Cache Analytics', shortLabel: 'Analytics', href: '/analytics', icon: BarChart3 },
  { label: 'Cache Explorer', shortLabel: 'Cache', href: '/cache', icon: Database },
  { label: 'AI Playground', shortLabel: 'Playground', href: '/playground', icon: MessageSquare },
  { label: 'Model Management', shortLabel: 'Models', href: '/models', icon: Cpu },
  { label: 'Request Logs', shortLabel: 'Logs', href: '/logs', icon: FileText },
  { label: 'Settings', shortLabel: 'Settings', href: '/settings', icon: Settings },
];

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const current = THEME_OPTIONS.find((item) => item.id === theme) ?? THEME_OPTIONS[0];

  return (
    <Menu as="div" className="relative">
      <MenuButton
        aria-label="Switch appearance theme"
        className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-xs font-medium text-[var(--foreground)] transition-colors hover:bg-[var(--muted)]"
      >
        <Palette className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
        <span className="hidden sm:inline">{current.label}</span>
      </MenuButton>

      <MenuItems
        aria-label="Theme options"
        className="absolute right-0 top-full z-40 mt-2 w-48 rounded-xl border border-[var(--border)] bg-[var(--card)] p-1.5 shadow-lg focus:outline-none"
      >
        <p className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
          Appearance
        </p>
        {THEME_OPTIONS.map((option) => {
          const active = option.id === theme;
          return (
            <MenuItem key={option.id}>
              <button
                type="button"
                role="menuitemradio"
                aria-checked={active}
                onClick={() => setTheme(option.id)}
                className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs font-medium transition-colors data-[focus]:bg-[var(--muted)] ${
                  active
                    ? 'bg-[var(--accent-soft)] text-[var(--accent)]'
                    : 'text-[var(--foreground)] hover:bg-[var(--muted)]'
                }`}
              >
                <span className="flex items-center gap-2">
                  <span
                    className="h-3.5 w-3.5 rounded-full border border-[var(--border)]"
                    style={{ backgroundColor: option.swatch }}
                    aria-hidden="true"
                  />
                  {option.label}
                </span>
                {active && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
              </button>
            </MenuItem>
          );
        })}
      </MenuItems>
    </Menu>
  );
}

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isOverview = pathname === '/';
  const isPlayground = pathname === '/playground';
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const dispatch = useAppDispatch();
  const { selectedDays, appliedCustom } = useAppSelector((state) => state.dateRange);
  const { data: statsData } = useGetCacheStatsQuery(undefined, { skip: !user || !isOverview });
  const currentPage =
    navigation.find(({ href }) => pathname === href || (href !== '/' && pathname.startsWith(`${href}/`))) ??
    navigation[0];

  useEffect(() => {
    if (!loading && !user) router.replace('/login');
  }, [loading, router, user]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--background)] text-sm text-[var(--muted-foreground)]">
        Checking sign-in…
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col bg-[var(--background)] text-[var(--foreground)] ${
        isPlayground ? 'h-screen overflow-hidden' : 'min-h-screen'
      }`}
    >
      {/* Top Navigation & Status Header */}
      <header className="sticky top-0 z-30 flex h-14 sm:h-16 shrink-0 items-center justify-between border-b border-[var(--border)] bg-[var(--card)]/95 px-3 backdrop-blur sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-2.5 rounded-lg pr-1 transition-opacity hover:opacity-90"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent)] text-[var(--accent-foreground)]">
              <Layers className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="hidden min-w-0 sm:block">
              <span className="block text-sm font-semibold tracking-tight text-[var(--foreground)]">
                Vector Cache
              </span>
            </span>
          </Link>

          <span className="hidden h-5 w-px bg-[var(--border)] sm:inline-block" aria-hidden="true" />

          <div className="min-w-0">
            <p className="hidden truncate text-[11px] text-[var(--muted-foreground)] sm:block">
              Workspace / {currentPage.label}
            </p>
            <h1 className="truncate text-sm font-medium text-[var(--foreground)]">{currentPage.label}</h1>
          </div>
        </div>

        <div className="flex items-center gap-2.5 sm:gap-3">
          {isOverview && (
            <div className="hidden lg:block">
              <DateRangeFilter
                selectedDays={selectedDays}
                appliedCustom={appliedCustom}
                defaultStartDate={statsData?.first_request_date}
                onSelectPreset={(days) => dispatch(setDatePreset(days))}
                onApplyCustom={(range) => dispatch(setCustomDateRange(range))}
              />
            </div>
          )}
          <ThemeSwitcher />
          <Link
            href="/settings"
            title={`${user.email} · Open Settings`}
            className="hidden items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--background)]/70 px-2.5 py-1 text-xs text-[var(--foreground)] transition-colors hover:bg-[var(--muted)] sm:flex"
          >
            <UserRound className="h-3.5 w-3.5 shrink-0 text-[var(--muted-foreground)]" aria-hidden="true" />
            <div className="min-w-0 leading-tight">
              <div className="max-w-[160px] truncate font-medium">{user.full_name}</div>
              <div className="max-w-[180px] truncate text-[10px] text-[var(--muted-foreground)]">{user.email}</div>
            </div>
          </Link>
          <button
            type="button"
            onClick={() => void logout()}
            aria-label="Log out"
            title="Log out"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--card)] px-2.5 py-1.5 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
          >
            <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden md:inline">Logout</span>
          </button>
        </div>
      </header>

      {/* Main Content Canvas */}
      <main
        className={
          isPlayground
            ? 'flex min-h-0 flex-1 flex-col overflow-hidden p-0'
            : 'mx-auto w-full max-w-[1440px] flex-1 px-3 pt-4 pb-20 sm:px-6 sm:pt-6 sm:pb-24'
        }
      >
        {children}
      </main>

      {/* Bottom Navigation Dock */}
      <div className="pointer-events-none sticky bottom-0 z-30 shrink-0 px-2 pb-2.5 pt-2 sm:px-6 sm:pb-4">
        <nav
          aria-label="Workspace bottom navigation"
          className="pointer-events-auto mx-auto grid w-full max-w-full grid-cols-7 items-center gap-0.5 rounded-2xl border border-[var(--border)] p-1 backdrop-blur-md sm:flex sm:w-fit sm:gap-1 sm:p-1.5"
          style={{
            backgroundColor: 'var(--dock-bg)',
            boxShadow: 'var(--dock-shadow)',
          }}
        >
          {navigation.map(({ label, shortLabel, href, icon: Icon }) => {
            const active = pathname === href || (href !== '/' && pathname.startsWith(`${href}/`));
            return (
              <Link
                key={href}
                href={href}
                aria-label={label}
                aria-current={active ? 'page' : undefined}
                className={`group relative flex flex-col items-center justify-center gap-0.5 rounded-xl px-1 py-1.5 text-[10px] font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] sm:shrink-0 sm:flex-row sm:gap-2 sm:px-3.5 sm:py-2 sm:text-xs sm:font-semibold ${
                  active
                    ? 'bg-[var(--accent)] text-[var(--accent-foreground)] shadow-xs'
                    : 'text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]'
                }`}
              >
                <Icon
                  className={`h-4 w-4 shrink-0 ${
                    active ? 'text-[var(--accent-foreground)]' : 'text-[var(--muted-foreground)] group-hover:text-[var(--foreground)]'
                  }`}
                  aria-hidden="true"
                />
                <span className="truncate max-w-full whitespace-nowrap">{shortLabel}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
