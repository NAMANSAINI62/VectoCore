'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authService } from './service';
import { useAuth } from './provider';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { Layers, AlertCircle } from 'lucide-react';

export function LoginForm() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
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
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center p-4">
      <Card className="w-full max-w-md border-zinc-200 dark:border-zinc-800">
        <CardHeader className="text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"><Layers className="h-5 w-5" /></div>
          <CardTitle className="text-xl">Sign In</CardTitle>
          <CardDescription>Enter your email and password to access your account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && <div className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-400"><AlertCircle className="h-4 w-4 shrink-0" /><span>{error}</span></div>}
            <Input id="email" type="email" label="Email Address" placeholder="name@example.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
            <div className="space-y-1">
              <div className="flex items-center justify-between"><label htmlFor="password" className="text-xs font-medium text-zinc-700 dark:text-zinc-300">Password</label></div>
              <Input id="password" type="password" placeholder="••••••••" value={password} onChange={(event) => setPassword(event.target.value)} required />
            </div>
            <Button type="submit" variant="primary" className="w-full" disabled={loading}>{loading ? 'Signing in...' : 'Sign In'}</Button>
            <div className="pt-2 text-center text-xs text-zinc-500 dark:text-zinc-400">Don&apos;t have an account? <Link href="/register" className="font-semibold text-zinc-900 hover:underline dark:text-zinc-100">Create one</Link></div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
