'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authService } from './service';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { Layers, AlertCircle, CheckCircle2 } from 'lucide-react';

export function RegisterForm() {
  const router = useRouter();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

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
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center p-4">
      <Card className="w-full max-w-md border-zinc-200 dark:border-zinc-800">
        <CardHeader className="text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Layers className="h-5 w-5" />
          </div>
          <CardTitle className="text-xl">Create Account</CardTitle>
          <CardDescription>Get started with Semantic Caching SaaS</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && <div className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-400"><AlertCircle className="h-4 w-4 shrink-0" /><span>{error}</span></div>}
            {success && <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400"><CheckCircle2 className="h-4 w-4 shrink-0" /><span>Account created! Redirecting to login...</span></div>}
            <Input id="fullName" type="text" label="Full Name" placeholder="John Doe" value={fullName} onChange={(event) => setFullName(event.target.value)} required />
            <Input id="email" type="email" label="Email Address" placeholder="name@example.com" value={email} onChange={(event) => setEmail(event.target.value)} required />
            <Input id="password" type="password" label="Password (min 8 characters)" placeholder="Enter Passward" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required />
            <Button type="submit" variant="primary" className="w-full" disabled={loading || success}>{loading ? 'Creating account...' : 'Create Account'}</Button>
            <div className="pt-2 text-center text-xs text-zinc-500 dark:text-zinc-400">Already have an account? <Link href="/login" className="font-semibold text-zinc-900 hover:underline dark:text-zinc-100">Sign In</Link></div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
