const DEFAULT_MODEL_STORAGE_KEY = 'vectocore_default_model';

export function getSavedDefaultModel(): { provider: string; modelId: string } | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(DEFAULT_MODEL_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { provider?: unknown; modelId?: unknown };
    if (typeof parsed.provider === 'string' && typeof parsed.modelId === 'string') {
      return { provider: parsed.provider, modelId: parsed.modelId };
    }
    return null;
  } catch {
    return null;
  }
}

export function saveDefaultModel(provider: string, modelId: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(DEFAULT_MODEL_STORAGE_KEY, JSON.stringify({ provider, modelId }));
  } catch {
    // Ignore storage errors
  }
}
