'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/features/auth/provider';
import { Button } from '@/components/ui/Button';
import { LogOut, User as UserIcon } from 'lucide-react';

export function Navbar() {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();

  if (pathname !== '/login' && pathname !== '/register') return null;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-[var(--border)] bg-[var(--card)]/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="text-sm font-semibold tracking-tight text-[var(--foreground)]">
          VectoCore
        </Link>

        <nav aria-label="Account navigation" className="flex items-center gap-3">
          {!loading && user ? (
            <>
              <span className="flex items-center gap-1.5 text-xs font-medium text-[var(--muted-foreground)]">
                <UserIcon className="h-3.5 w-3.5" aria-hidden="true" />
                {user.full_name}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void logout()}
                className="flex items-center gap-1 text-xs"
              >
                <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Log out</span>
              </Button>
            </>
          ) : !loading ? (
            <Link href="/login">
              <Button variant="primary" size="sm" className="text-xs">
                Sign in
              </Button>
            </Link>
          ) : null}
        </nav>
      </div>
    </header>
  );
}
