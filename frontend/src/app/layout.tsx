import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/features/auth/provider';
import { ReduxProvider } from '@/store/provider';
import { Navbar } from '@/components/Navbar';
import { ThemeProvider } from '@/components/ThemeProvider';

export const metadata: Metadata = {
  title: 'VectoCore — AI Semantic Cache',
  description: 'Semantic Cache Engine & AI Workspace',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className="min-h-screen bg-[var(--background)] font-sans antialiased text-[var(--foreground)]"
      >
        <ReduxProvider>
          <ThemeProvider>
            <AuthProvider>
              <Navbar />
              <div>{children}</div>
            </AuthProvider>
          </ThemeProvider>
        </ReduxProvider>
      </body>
    </html>
  );
}
