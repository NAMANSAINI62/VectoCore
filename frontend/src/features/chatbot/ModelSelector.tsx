'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpenCheck,
  Check,
  ChevronRight,
  Cpu,
  Scale,
  Search,
  Sparkles,
  Wand2,
  X,
  Zap,
} from 'lucide-react';

export type Model = {
  id: string;
  name: string;
  provider: string;
  tier?: string | null;
};

export type Provider = {
  id: string;
  configured: boolean;
  models: string[];
};

const PROVIDER_LABELS: Record<string, string> = {
  groq: 'Groq',
  openrouter: 'OpenRouter',
  gemini: 'Gemini',
  cohere: 'Cohere',
  nvidia: 'NVIDIA',
};

type PaneKey = 'auto' | 'deep_research' | 'complex' | 'balanced' | 'fast';
type TierKey = Exclude<PaneKey, 'auto'>;

const MODEL_TIERS: ReadonlyArray<{
  key: TierKey;
  label: string;
  shortLabel: string;
  hint: string;
}> = [
  { key: 'deep_research', label: 'Deep Research', shortLabel: 'Deep Research', hint: 'Heavy synthesis & deep analysis' },
  { key: 'complex', label: 'Complex Queries', shortLabel: 'Complex', hint: 'Architecture, debug & high-parameter models' },
  { key: 'balanced', label: 'Balanced Queries', shortLabel: 'Balanced', hint: 'Code, comparisons & everyday chat' },
  { key: 'fast', label: 'Fast Queries', shortLabel: 'Fast', hint: 'Instant replies & low-latency models' },
];

export function formatProviderLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

function getModelTier(m: Model): TierKey {
  if (m.provider === 'gemini') {
    const t = m.tier as TierKey | undefined;
    if (t === 'deep_research' || t === 'complex' || t === 'balanced' || t === 'fast') {
      return t;
    }
    return 'balanced';
  }
  const key = `${m.id} ${m.name}`.toLowerCase();
  if (key.includes('120b') || key.includes('340b') || key.includes('ultra')) {
    return 'complex';
  }
  if (key.includes('flash') || key.includes('bolt')) {
    return 'fast';
  }
  return 'balanced';
}

function getProviderIcon(provider: string) {
  if (provider === 'groq') {
    return <Zap className="h-3.5 w-3.5 text-amber-500 dark:text-amber-400" />;
  }
  if (provider === 'gemini') {
    return <Sparkles className="h-3.5 w-3.5 text-sky-500 dark:text-sky-400" />;
  }
  return <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" />;
}

function getPaneIcon(pane: PaneKey) {
  if (pane === 'auto') return <Wand2 className="h-3.5 w-3.5 text-sky-500 dark:text-sky-400" />;
  if (pane === 'deep_research') return <BookOpenCheck className="h-3.5 w-3.5 text-violet-500 dark:text-violet-400" />;
  if (pane === 'complex') return <Cpu className="h-3.5 w-3.5 text-sky-500 dark:text-sky-400" />;
  if (pane === 'balanced') return <Scale className="h-3.5 w-3.5 text-emerald-500 dark:text-emerald-400" />;
  return <Zap className="h-3.5 w-3.5 text-amber-500 dark:text-amber-400" />;
}

export type ModelSelectorProps = {
  models: Model[];
  providers: Provider[];
  currentProvider: string;
  currentModelId: string;
  onSelectModel: (provider: string, modelId: string) => void;
  isOpen: boolean;
  onClose: () => void;
};

/**
 * Unified Two-Pane Frosted Glass Model Selector:
 * - Single translucent blurred container matching the top navigation bar
 * - Left rail: Smart Auto + 4 balanced query tiers (Deep Research, Complex, Balanced, Fast)
 * - Right pane: Large, stationary, easy-to-click model cards across all providers
 */
export function ModelSelector({
  models,
  providers,
  currentProvider,
  currentModelId,
  onSelectModel,
  isOpen,
  onClose,
}: ModelSelectorProps) {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activePane, setActivePane] = useState<PaneKey>('auto');
  const [highlightedIndex, setHighlightedIndex] = useState<number>(0);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const hoverTimerRef = useRef<number | null>(null);

  const clearHoverTimer = () => {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  };

  const schedulePane = (nextPane: PaneKey) => {
    clearHoverTimer();
    if (nextPane === activePane) return;
    hoverTimerRef.current = window.setTimeout(() => {
      setActivePane(nextPane);
      hoverTimerRef.current = null;
    }, 110);
  };

  const configuredMap = useMemo(() => {
    const map = new Map<string, boolean>();
    for (const p of providers) {
      map.set(p.id, p.configured);
    }
    return map;
  }, [providers]);

  const geminiConfigured = configuredMap.get('gemini') ?? false;

  const geminiAutoModel = useMemo(
    () => models.find((m) => m.provider === 'gemini' && m.id === 'gemini-auto') ?? null,
    [models],
  );

  // Distribute all models (Gemini + other providers) across Deep Research, Complex, Balanced, and Fast
  const tierModels = useMemo(() => {
    const buckets: Record<TierKey, Model[]> = {
      deep_research: [],
      complex: [],
      balanced: [],
      fast: [],
    };
    const seen = new Set<string>();
    for (const m of models) {
      if (m.provider === 'gemini' && m.id === 'gemini-auto') {
        continue;
      }
      const dedupKey = `${m.provider}:${m.id}`;
      if (seen.has(dedupKey)) continue;
      seen.add(dedupKey);
      const key = getModelTier(m);
      buckets[key].push(m);
    }
    for (const tierKey of Object.keys(buckets) as TierKey[]) {
      buckets[tierKey].sort((a, b) => {
        const aConf = configuredMap.get(a.provider) ?? false;
        const bConf = configuredMap.get(b.provider) ?? false;
        return aConf === bConf ? 0 : aConf ? -1 : 1;
      });
    }
    return buckets;
  }, [models, configuredMap]);

  // Open on the pane corresponding to the currently active model
  useEffect(() => {
    if (!isOpen) return;
    clearHoverTimer();
    setSearchQuery('');
    setHighlightedIndex(0);

    if (currentProvider === 'gemini' && currentModelId === 'gemini-auto') {
      setActivePane('auto');
      return;
    }
    const current = models.find((m) => m.provider === currentProvider && m.id === currentModelId);
    if (current) {
      setActivePane(getModelTier(current));
    } else {
      setActivePane(geminiAutoModel ? 'auto' : 'balanced');
    }
    return () => clearHoverTimer();
  }, [isOpen, currentProvider, currentModelId, models, geminiAutoModel]);

  const filteredSearchModels = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return [];
    const list = models.filter((m) => {
      const effectiveTier = m.id === 'gemini-auto' ? 'auto' : getModelTier(m);
      return (
        m.name.toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q) ||
        formatProviderLabel(m.provider).toLowerCase().includes(q) ||
        effectiveTier.replace('_', ' ').includes(q)
      );
    });
    return [...list].sort((a, b) => {
      const aConf = configuredMap.get(a.provider) ?? false;
      const bConf = configuredMap.get(b.provider) ?? false;
      return aConf === bConf ? 0 : aConf ? -1 : 1;
    });
  }, [models, searchQuery, configuredMap]);

  useEffect(() => {
    if (highlightedIndex >= filteredSearchModels.length) {
      setHighlightedIndex(0);
    }
  }, [filteredSearchModels.length, highlightedIndex]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!searchQuery.trim() || filteredSearchModels.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlightedIndex((prev) => (prev + 1) % filteredSearchModels.length);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlightedIndex((prev) => (prev - 1 + filteredSearchModels.length) % filteredSearchModels.length);
      return;
    }
    if (event.key === 'Enter' && filteredSearchModels[highlightedIndex]) {
      const chosen = filteredSearchModels[highlightedIndex];
      if (configuredMap.get(chosen.provider) ?? false) {
        event.preventDefault();
        onSelectModel(chosen.provider, chosen.id);
        onClose();
      }
    }
  };

  if (!isOpen) return null;

  const isSearching = searchQuery.trim().length > 0;
  const activeTierInfo = MODEL_TIERS.find((t) => t.key === activePane) ?? null;

  return (
    <div
      onKeyDown={handleKeyDown}
      className="w-[376px] sm:w-[444px] max-w-[92vw] select-none"
    >
      <div
        className="rounded-2xl border p-2.5 backdrop-blur-2xl animate-in fade-in zoom-in-95 duration-150"
        style={{
          background: 'color-mix(in srgb, var(--card) 72%, transparent)',
          borderColor: 'var(--border)',
          color: 'var(--foreground)',
          boxShadow: '0 16px 40px rgba(15, 23, 42, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.35)',
        }}
      >
        {/* Top Search Bar */}
        <div
          className="flex items-center gap-2 pb-2 mb-2 border-b"
          style={{ borderColor: 'var(--border)' }}
        >
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--muted-foreground)]" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setHighlightedIndex(0);
              }}
              placeholder="Search models or tiers..."
              className="h-8 w-full rounded-xl border pl-8 pr-7 text-[12px] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] outline-none focus:border-[var(--accent)]"
              style={{
                background: 'color-mix(in srgb, var(--background) 65%, transparent)',
                borderColor: 'var(--border)',
              }}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <span
            className="shrink-0 rounded-lg border px-2 py-1 text-[10.5px] font-medium text-[var(--muted-foreground)]"
            style={{
              background: 'color-mix(in srgb, var(--background) 55%, transparent)',
              borderColor: 'var(--border)',
            }}
          >
            {isSearching ? filteredSearchModels.length : models.length} models
          </span>
        </div>

        {isSearching ? (
          /* Search Results View */
          <div className="h-[258px] overflow-y-auto custom-scrollbar space-y-1.5 pr-1">
            {filteredSearchModels.length === 0 ? (
              <div className="flex h-full items-center justify-center text-xs text-[var(--muted-foreground)]">
                No matching models found.
              </div>
            ) : (
              filteredSearchModels.map((m, idx) => {
                const isSelected = m.id === currentModelId && m.provider === currentProvider;
                const isConfigured = configuredMap.get(m.provider) ?? false;
                const isHighlighted = idx === highlightedIndex;
                const tierLabel = m.id === 'gemini-auto' ? 'auto' : getModelTier(m).replace('_', ' ');
                return (
                  <button
                    type="button"
                    key={`${m.provider}-${m.id}`}
                    disabled={!isConfigured}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    onClick={() => {
                      if (isConfigured) {
                        onSelectModel(m.provider, m.id);
                        onClose();
                      }
                    }}
                    className={`flex h-[44px] w-full items-center justify-between rounded-xl px-3 text-left border transition-colors ${
                      isSelected
                        ? 'border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--foreground)]'
                        : isHighlighted
                        ? 'border-[var(--border)] bg-[var(--background)]/75 text-[var(--foreground)]'
                        : 'border-transparent bg-[var(--background)]/45 text-[var(--foreground)] hover:bg-[var(--background)]/75 hover:border-[var(--border)]'
                    } ${!isConfigured ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <div
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border"
                        style={{
                          background: 'color-mix(in srgb, var(--card) 80%, transparent)',
                          borderColor: 'var(--border)',
                        }}
                      >
                        {getProviderIcon(m.provider)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold truncate text-[12.5px] leading-tight text-[var(--foreground)]">
                          {m.name}
                        </div>
                        <div className="text-[10px] text-[var(--muted-foreground)] truncate leading-tight">
                          {formatProviderLabel(m.provider)} · {tierLabel}
                        </div>
                      </div>
                    </div>
                    {isSelected && (
                      <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white">
                        <Check className="h-3 w-3 stroke-[3]" />
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>
        ) : (
          /* Unified Stable Two-Pane Layout */
          <div className="grid grid-cols-[148px_1fr] sm:grid-cols-[164px_1fr] gap-2.5 h-[258px]">
            {/* Left Rail: Tiers */}
            <div
              className="flex flex-col gap-1 border-r pr-2 overflow-y-auto custom-scrollbar"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="px-1.5 pt-0.5 pb-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                Tiers
              </div>

              {geminiAutoModel && (
                <button
                  type="button"
                  disabled={!geminiConfigured}
                  onMouseEnter={() => schedulePane('auto')}
                  onClick={() => {
                    clearHoverTimer();
                    setActivePane('auto');
                    if (geminiConfigured) {
                      onSelectModel('gemini', geminiAutoModel.id);
                      onClose();
                    }
                  }}
                  className={`flex h-[36px] w-full items-center justify-between rounded-xl px-2 text-left text-[11.5px] font-medium border transition-colors ${
                    activePane === 'auto'
                      ? 'border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--foreground)] font-semibold'
                      : currentProvider === 'gemini' && currentModelId === 'gemini-auto'
                      ? 'border-[var(--border)] bg-[var(--background)]/65 text-[var(--foreground)]'
                      : 'border-transparent bg-transparent text-[var(--muted-foreground)] hover:bg-[var(--background)]/55 hover:text-[var(--foreground)]'
                  } ${!geminiConfigured ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  <span className="flex items-center gap-2 truncate">
                    {getPaneIcon('auto')}
                    <span className="truncate">Gemini Auto</span>
                  </span>
                  {currentProvider === 'gemini' && currentModelId === 'gemini-auto' && (
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] shrink-0" />
                  )}
                </button>
              )}

              {MODEL_TIERS.map((tier) => {
                const list = tierModels[tier.key];
                if (list.length === 0) return null;
                const isSelectedInTier = list.some(
                  (m) => m.provider === currentProvider && m.id === currentModelId,
                );
                const isActive = activePane === tier.key;

                return (
                  <button
                    key={tier.key}
                    type="button"
                    onMouseEnter={() => schedulePane(tier.key)}
                    onClick={() => {
                      clearHoverTimer();
                      setActivePane(tier.key);
                    }}
                    className={`flex h-[36px] w-full items-center justify-between rounded-xl px-2 text-left text-[11.5px] font-medium border transition-colors cursor-pointer ${
                      isActive
                        ? 'border-[var(--border)] bg-[var(--background)]/75 text-[var(--foreground)] font-semibold shadow-sm'
                        : isSelectedInTier
                        ? 'border-[var(--border)]/70 bg-[var(--background)]/45 text-[var(--foreground)]'
                        : 'border-transparent bg-transparent text-[var(--muted-foreground)] hover:bg-[var(--background)]/55 hover:text-[var(--foreground)]'
                    }`}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="shrink-0">{getPaneIcon(tier.key)}</span>
                      <span className="truncate">{tier.shortLabel}</span>
                    </span>
                    <span className="flex items-center gap-1 shrink-0 text-[var(--muted-foreground)]">
                      {isSelectedInTier && <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />}
                      <span className="text-[10px] tabular-nums">{list.length}</span>
                      <ChevronRight className="h-3 w-3 opacity-70" />
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Right Pane: Locked Stationary Selection Area */}
            <div
              onMouseEnter={() => clearHoverTimer()}
              className="flex flex-col min-w-0 overflow-hidden"
            >
              {activePane === 'auto' && geminiAutoModel ? (
                <div className="flex flex-col h-full justify-between p-1">
                  <div>
                    <div className="text-[12.5px] font-semibold text-[var(--foreground)]">Gemini Auto</div>
                    <p className="mt-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                      Automatically picks the fastest or deepest Gemini model based on your query and healthy free-tier quota.
                    </p>
                    <button
                      type="button"
                      disabled={!geminiConfigured}
                      onClick={() => {
                        if (geminiConfigured) {
                          onSelectModel('gemini', geminiAutoModel.id);
                          onClose();
                        }
                      }}
                      className={`mt-3 flex h-[44px] w-full items-center justify-between rounded-xl px-3 border transition-colors cursor-pointer ${
                        currentProvider === 'gemini' && currentModelId === 'gemini-auto'
                          ? 'border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--foreground)]'
                          : 'border-[var(--border)] bg-[var(--background)]/60 text-[var(--foreground)] hover:bg-[var(--accent)]/10 hover:border-[var(--accent)]/50'
                      }`}
                    >
                      <span className="flex items-center gap-2.5 text-[12.5px] font-semibold">
                        <Wand2 className="h-4 w-4 text-sky-500 dark:text-sky-400" />
                        Use Smart Auto Router
                      </span>
                      {currentProvider === 'gemini' && currentModelId === 'gemini-auto' && (
                        <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent)] text-white">
                          <Check className="h-3 w-3 stroke-[3]" />
                        </div>
                      )}
                    </button>
                  </div>

                  <div
                    className="rounded-xl border px-2.5 py-2 text-[10.5px] text-[var(--muted-foreground)]"
                    style={{
                      background: 'color-mix(in srgb, var(--background) 50%, transparent)',
                      borderColor: 'var(--border)',
                    }}
                  >
                    Or hover/click a tier on the left to pick any model manually.
                  </div>
                </div>
              ) : activeTierInfo ? (
                <div className="flex flex-col h-full">
                  <div className="px-1 pb-2">
                    <div className="flex items-center gap-1.5 text-[12px] font-semibold text-[var(--foreground)]">
                      {getPaneIcon(activeTierInfo.key)}
                      <span>{activeTierInfo.label}</span>
                    </div>
                    <div className="text-[10px] text-[var(--muted-foreground)] mt-0.5">{activeTierInfo.hint}</div>
                  </div>
                  <div className="flex-1 overflow-y-auto custom-scrollbar space-y-1.5 pr-1">
                    {tierModels[activeTierInfo.key].map((m) => {
                      const isSelected = currentProvider === m.provider && currentModelId === m.id;
                      const isConfigured = configuredMap.get(m.provider) ?? false;
                      return (
                        <button
                          type="button"
                          key={`${m.provider}-${m.id}`}
                          disabled={!isConfigured}
                          onClick={() => {
                            if (isConfigured) {
                              onSelectModel(m.provider, m.id);
                              onClose();
                            }
                          }}
                          className={`flex h-[44px] w-full items-center justify-between rounded-xl px-3 text-left border transition-colors ${
                            isSelected
                              ? 'border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--foreground)] font-semibold'
                              : 'border-[var(--border)]/70 bg-[var(--background)]/55 text-[var(--foreground)] hover:bg-[var(--background)]/85 hover:border-[var(--border)]'
                          } ${!isConfigured ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}
                        >
                          <div className="flex items-center gap-2 min-w-0 flex-1 pr-2">
                            <span className="shrink-0">{getProviderIcon(m.provider)}</span>
                            <div className="min-w-0 flex-1">
                              <div className="text-[12.5px] font-medium truncate leading-tight text-[var(--foreground)]">
                                {m.name}
                              </div>
                              <div className="text-[10px] text-[var(--muted-foreground)] truncate leading-tight">
                                {formatProviderLabel(m.provider)}
                                {!isConfigured ? ' · Unconfigured' : ''}
                              </div>
                            </div>
                          </div>
                          {isSelected && (
                            <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white">
                              <Check className="h-2.5 w-2.5 stroke-[3]" />
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
