'use client';

import { createContext, useContext, useEffect, useState } from 'react';

export type AppTheme = 'mint' | 'sage' | 'mocha' | 'lavender' | 'glacier';

export type ThemeOption = {
  id: AppTheme;
  label: string;
  swatch: string;
  secondarySwatch: string;
  accentSwatch: string;
};

export const THEME_OPTIONS: ThemeOption[] = [
  { id: 'mint', label: 'Botanical Ink', swatch: '#E5EFE9', secondarySwatch: '#FFFFFF', accentSwatch: '#0D9488' },
  { id: 'sage', label: 'Sage Paper', swatch: '#9CAF88', secondarySwatch: '#F7F5EF', accentSwatch: '#E8412C' },
  { id: 'mocha', label: 'Mocha Cream', swatch: '#F2E8DA', secondarySwatch: '#E8DBC8', accentSwatch: '#2C74B3' },
  { id: 'lavender', label: 'Lavender Cloud', swatch: '#F2EFFB', secondarySwatch: '#E3DDF7', accentSwatch: '#6D4AFF' },
  { id: 'glacier', label: 'Glacier Sky', swatch: '#EAF4FC', secondarySwatch: '#D6E9F8', accentSwatch: '#0284C7' },
];

const STORAGE_KEY = 'vector_cache_theme';

type ThemeContextValue = {
  theme: AppTheme;
  setTheme: (next: AppTheme) => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'mint',
  setTheme: () => {},
});

function applyThemeToDom(theme: AppTheme) {
  const root = document.documentElement;
  root.setAttribute('data-theme', theme);
  root.classList.remove('dark');
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>('mint');

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY) as AppTheme | null;
      if (saved && THEME_OPTIONS.some((item) => item.id === saved)) {
        setThemeState(saved);
        applyThemeToDom(saved);
        return;
      }
    } catch {
      // Ignore storage access errors
    }
    applyThemeToDom('mint');
  }, []);

  const setTheme = (next: AppTheme) => {
    setThemeState(next);
    applyThemeToDom(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Ignore storage access errors
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
