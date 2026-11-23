'use client';

import React, { useEffect } from 'react';
import { Provider } from 'react-redux';
import { store } from './index';
import { cacheApi } from './cacheApi';

const GLOBAL_SYNC_INTERVAL_MS = 3000;

function GlobalAutoSync() {
  useEffect(() => {
    const triggerSync = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }
      if (
        typeof window !== 'undefined' &&
        (window.location.pathname === '/login' || window.location.pathname === '/register')
      ) {
        return;
      }
      store.dispatch(
        cacheApi.util.invalidateTags(['CacheEntries', 'CacheStats', 'Models', 'Providers'])
      );
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('vectocore:sync'));
      }
    };

    const intervalId = window.setInterval(triggerSync, GLOBAL_SYNC_INTERVAL_MS);
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        triggerSync();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('focus', triggerSync);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('focus', triggerSync);
    };
  }, []);

  return null;
}

export function ReduxProvider({ children }: { children: React.ReactNode }) {
  return (
    <Provider store={store}>
      <GlobalAutoSync />
      {children}
    </Provider>
  );
}
