'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpenCheck,
  Check,
  ChevronRight,
  Cpu,
  Layers,
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

type PaneKey = 'auto' | 'deep_research' | 'complex' | 'balanced' | 'fast' | 'others';

const GEMINI_TIERS: ReadonlyArray<{
  key: Exclude<PaneKey, 'auto' | 'others'>;
  label: string;
  shortLabel: string;
  hint: string;
}> = [
  { key: 'deep_research', label: 'Deep Research', shortLabel: 'Deep Research', hint: 'Heavy synthesis & deep analysis' },
  { key: 'complex', label: 'Complex Queries', shortLabel: 'Complex', hint: 'Architecture, debug & tradeoffs' },
  { key: 'balanced', label: 'Balanced Queries', shortLabel: 'Balanced', hint: 'Code, comparisons & everyday chat' },
  { key: 'fast', label: 'Fast Queries', shortLabel: 'Fast', hint: 'Instant replies & high daily quota' },
];

export function formatProviderLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

function getProviderIcon(provider: string) {
  if (provider === 'groq') {
    return <Zap className="h-3.5 w-3.5 text-amber-300" />;
  }
  if (provider === 'gemini') {
    return <Sparkles className="h-3.5 w-3.5 text-sky-300" />;
  }
  return <Sparkles className="h-3.5 w-3.5 text-neutral-300" />;
}

function getPaneIcon(pane: PaneKey) {
  if (pane === 'auto') return <Wand2 className="h-3.5 w-3.5 text-sky-300" />;
  if (pane === 'deep_research') return <BookOpenCheck className="h-3.5 w-3.5 text-violet-300" />;
  if (pane === 'complex') return <Cpu className="h-3.5 w-3.5 text-sky-300" />;
  if (pane === 'balanced') return <Scale className="h-3.5 w-3.5 text-emerald-300" />;
  if (pane === 'fast') return <Zap className="h-3.5 w-3.5 text-amber-300" />;
  return <Layers className="h-3.5 w-3.5 text-neutral-300" />;
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
 * Unified Two-Pane Model Selector:
 * - Single solid glass container (no external floating edge flyouts or layout shifts)
 * - Left rail: Gemini Auto, 4 Gemini query tiers, and Other Providers
 * - Right pane: Large, stationary, easy-to-click short-named model cards
 * - Anti-jitter hover-intent lock prevents accidental tier switches on diagonal laptop trackpad moves
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

  // Deduplicated Gemini tier buckets driven by backend model metadata
  const geminiTierModels = useMemo(() => {
    const buckets: Record<Exclude<PaneKey, 'auto' | 'others'>, Model[]> = {
      deep_research: [],
      complex: [],
      balanced: [],
      fast: [],
    };
    const seen = new Set<string>();
    for (const m of models) {
      if (m.provider !== 'gemini' || m.id === 'gemini-auto' || seen.has(m.id)) {
        continue;
      }
      const key = (m.tier as Exclude<PaneKey, 'auto' | 'others'> | undefined) ?? 'balanced';
      if (key in buckets) {
        buckets[key].push(m);
        seen.add(m.id);
      }
    }
    return buckets;
  }, [models]);

  const otherModels = useMemo(() => {
    const list = models.filter((m) => m.provider !== 'gemini');
    return [...list].sort((a, b) => {
      const aConf = configuredMap.get(a.provider) ?? false;
      const bConf = configuredMap.get(b.provider) ?? false;
      return aConf === bConf ? 0 : aConf ? -1 : 1;
    });
  }, [models, configuredMap]);

  // Open on the pane corresponding to the currently active model
  useEffect(() => {
    if (!isOpen) return;
    clearHoverTimer();
    setSearchQuery('');
    setHighlightedIndex(0);

    if (currentProvider !== 'gemini') {
      setActivePane('others');
      return;
    }
    if (currentModelId === 'gemini-auto') {
      setActivePane('auto');
      return;
    }
    const current = models.find((m) => m.provider === 'gemini' && m.id === currentModelId);
    const tier = current?.tier as PaneKey | undefined;
    if (tier && (tier === 'deep_research' || tier === 'complex' || tier === 'balanced' || tier === 'fast')) {
      setActivePane(tier);
    } else {
      setActivePane('auto');
    }
    return () => clearHoverTimer();
  }, [isOpen, currentProvider, currentModelId, models]);

  const filteredSearchModels = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return [];
    const list = models.filter((m) => {
      return (
        m.name.toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q) ||
        formatProviderLabel(m.provider).toLowerCase().includes(q) ||
        (m.tier ?? '').replace('_', ' ').includes(q)
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
  const activeTierInfo = GEMINI_TIERS.find((t) => t.key === activePane) ?? null;

  return (
    <div
      onKeyDown={handleKeyDown}
      className="w-[376px] sm:w-[436px] max-w-[92vw] select-none"
    >
      <div
        className="rounded-2xl border border-white/[0.16] p-2.5 text-neutral-100 backdrop-blur-2xl animate-in fade-in zoom-in-95 duration-150"
        style={{
          background: 'linear-gradient(180deg, rgba(27, 32, 43, 0.98) 0%, rgba(17, 21, 28, 0.99) 100%)',
          boxShadow: '0 20px 48px rgba(0, 0, 0, 0.68), inset 0 1px 0 rgba(255, 255, 255, 0.14)',
        }}
      >
        {/* Top Search Bar */}
        <div className="flex items-center gap-2 pb-2 mb-2 border-b border-white/[0.08]">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-neutral-400" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setHighlightedIndex(0);
              }}
              placeholder="Search models or tiers..."
              className="h-8 w-full rounded-xl border border-white/[0.10] bg-black/35 pl-8 pr-7 text-[12px] text-neutral-100 placeholder:text-neutral-400 outline-none focus:border-sky-400/50"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-200"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <span className="shrink-0 rounded-lg bg-white/[0.05] px-2 py-1 text-[10.5px] font-medium text-neutral-400">
            {isSearching ? filteredSearchModels.length : models.length} models
          </span>
        </div>

        {isSearching ? (
          /* Search Results View */
          <div className="h-[248px] overflow-y-auto custom-scrollbar space-y-1.5 pr-1">
            {filteredSearchModels.length === 0 ? (
              <div className="flex h-full items-center justify-center text-xs text-neutral-400">
                No matching models found.
              </div>
            ) : (
              filteredSearchModels.map((m, idx) => {
                const isSelected = m.id === currentModelId && m.provider === currentProvider;
                const isConfigured = configuredMap.get(m.provider) ?? false;
                const isHighlighted = idx === highlightedIndex;
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
                    className={`flex h-[42px] w-full items-center justify-between rounded-xl px-3 text-left border transition-colors ${
                      isSelected
                        ? 'bg-sky-500/20 border-sky-400/45 text-white'
                        : isHighlighted
                        ? 'bg-white/[0.10] border-white/[0.16] text-neutral-100'
                        : 'bg-white/[0.04] border-transparent text-neutral-200 hover:bg-white/[0.09]'
                    } ${!isConfigured ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-black/35 border border-white/10">
                        {getProviderIcon(m.provider)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold truncate text-[12.5px] leading-tight">{m.name}</div>
                        <div className="text-[10px] text-neutral-400 truncate leading-tight">
                          {formatProviderLabel(m.provider)}
                          {m.tier && m.tier !== 'auto' ? ` · ${m.tier.replace('_', ' ')}` : ''}
                        </div>
                      </div>
                    </div>
                    {isSelected && (
                      <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-sky-400 text-slate-950">
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
            {/* Left Rail: Categories */}
            <div className="flex flex-col gap-1 border-r border-white/[0.08] pr-2 overflow-y-auto custom-scrollbar">
              <div className="px-1.5 pt-0.5 pb-0.5 text-[10px] font-medium text-neutral-400">
                Gemini
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
                  className={`flex h-[34px] w-full items-center justify-between rounded-xl px-2 text-left text-[11.5px] font-medium border transition-colors ${
                    activePane === 'auto'
                      ? 'bg-sky-500/20 border-sky-400/40 text-white'
                      : currentProvider === 'gemini' && currentModelId === 'gemini-auto'
                      ? 'bg-white/[0.09] border-white/15 text-white'
                      : 'bg-transparent border-transparent text-neutral-300 hover:bg-white/[0.07]'
                  } ${!geminiConfigured ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  <span className="flex items-center gap-2 truncate">
                    {getPaneIcon('auto')}
                    <span className="truncate">Gemini Auto</span>
                  </span>
                  {currentProvider === 'gemini' && currentModelId === 'gemini-auto' && (
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-400 shrink-0" />
                  )}
                </button>
              )}

              {GEMINI_TIERS.map((tier) => {
                const list = geminiTierModels[tier.key];
                if (list.length === 0) return null;
                const isSelectedInTier =
                  currentProvider === 'gemini' && list.some((m) => m.id === currentModelId);
                const isActive = activePane === tier.key;

                return (
                  <button
                    key={tier.key}
                    type="button"
                    disabled={!geminiConfigured}
                    onMouseEnter={() => schedulePane(tier.key)}
                    onClick={() => {
                      clearHoverTimer();
                      setActivePane(tier.key);
                    }}
                    className={`flex h-[34px] w-full items-center justify-between rounded-xl px-2 text-left text-[11.5px] font-medium border transition-colors ${
                      isActive
                        ? 'bg-white/[0.13] border-white/25 text-white'
                        : isSelectedInTier
                        ? 'bg-white/[0.07] border-white/15 text-neutral-100'
                        : 'bg-transparent border-transparent text-neutral-300 hover:bg-white/[0.07]'
                    } ${!geminiConfigured ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="shrink-0">{getPaneIcon(tier.key)}</span>
                      <span className="truncate">{tier.shortLabel}</span>
                    </span>
                    <span className="flex items-center gap-1 shrink-0 text-neutral-400">
                      {isSelectedInTier && <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />}
                      <ChevronRight className="h-3 w-3 opacity-70" />
                    </span>
                  </button>
                );
              })}

              {otherModels.length > 0 && (
                <>
                  <div className="my-1 border-t border-white/[0.08]" />
                  <button
                    type="button"
                    onMouseEnter={() => schedulePane('others')}
                    onClick={() => {
                      clearHoverTimer();
                      setActivePane('others');
                    }}
                    className={`flex h-[34px] w-full items-center justify-between rounded-xl px-2 text-left text-[11.5px] font-medium border transition-colors ${
                      activePane === 'others'
                        ? 'bg-white/[0.13] border-white/25 text-white'
                        : currentProvider !== 'gemini'
                        ? 'bg-white/[0.07] border-white/15 text-neutral-100'
                        : 'bg-transparent border-transparent text-neutral-300 hover:bg-white/[0.07]'
                    }`}
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="shrink-0">{getPaneIcon('others')}</span>
                      <span className="truncate">Other AI</span>
                    </span>
                    <span className="flex items-center gap-1 shrink-0 text-neutral-400">
                      {currentProvider !== 'gemini' && (
                        <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
                      )}
                      <span className="text-[10px]">{otherModels.length}</span>
                    </span>
                  </button>
                </>
              )}
            </div>

            {/* Right Pane: Locked Stationary Selection Area */}
            <div
              onMouseEnter={() => clearHoverTimer()}
              className="flex flex-col min-w-0 overflow-hidden"
            >
              {activePane === 'auto' && geminiAutoModel ? (
                <div className="flex flex-col h-full justify-between p-1">
                  <div>
                    <div className="text-[12.5px] font-semibold text-white">Gemini Auto</div>
                    <p className="mt-1 text-[11px] leading-relaxed text-neutral-400">
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
                      className={`mt-3 flex h-[44px] w-full items-center justify-between rounded-xl px-3 border transition-colors ${
                        currentProvider === 'gemini' && currentModelId === 'gemini-auto'
                          ? 'bg-sky-500/20 border-sky-400/50 text-white'
                          : 'bg-white/[0.07] border-white/15 text-white hover:bg-sky-500/15 hover:border-sky-400/40'
                      }`}
                    >
                      <span className="flex items-center gap-2.5 text-[12.5px] font-semibold">
                        <Wand2 className="h-4 w-4 text-sky-300" />
                        Use Smart Auto Router
                      </span>
                      {currentProvider === 'gemini' && currentModelId === 'gemini-auto' && (
                        <div className="flex h-5 w-5 items-center justify-center rounded-full bg-sky-400 text-slate-950">
                          <Check className="h-3 w-3 stroke-[3]" />
                        </div>
                      )}
                    </button>
                  </div>

                  <div className="rounded-xl border border-white/[0.07] bg-black/25 px-2.5 py-2 text-[10.5px] text-neutral-400">
                    Or hover/click a tier on the left to pick a manual Gemini model.
                  </div>
                </div>
              ) : activePane === 'others' ? (
                <div className="flex flex-col h-full">
                  <div className="px-1 pb-2">
                    <div className="text-[12px] font-semibold text-white">Other Providers</div>
                    <div className="text-[10px] text-neutral-400">Groq, OpenRouter, Cohere &amp; NVIDIA</div>
                  </div>
                  <div className="flex-1 overflow-y-auto custom-scrollbar space-y-1.5 pr-1">
                    {otherModels.map((m) => {
                      const isSelected = m.id === currentModelId && m.provider === currentProvider;
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
                          className={`flex h-[40px] w-full items-center justify-between rounded-xl px-2.5 text-left border transition-colors ${
                            isSelected
                              ? 'bg-sky-500/20 border-sky-400/45 text-white'
                              : 'bg-white/[0.04] border-transparent text-neutral-200 hover:bg-white/[0.11] hover:border-white/15'
                          } ${!isConfigured ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}
                        >
                          <div className="min-w-0 flex-1 pr-2">
                            <div className="text-[12px] font-semibold truncate">{m.name}</div>
                            <div className="text-[10px] text-neutral-400 truncate">
                              {formatProviderLabel(m.provider)}
                              {!isConfigured ? ' · Unconfigured' : ''}
                            </div>
                          </div>
                          {isSelected && (
                            <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-400 text-slate-950">
                              <Check className="h-2.5 w-2.5 stroke-[3]" />
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : activeTierInfo ? (
                <div className="flex flex-col h-full">
                  <div className="px-1 pb-2">
                    <div className="flex items-center gap-1.5 text-[12px] font-semibold text-white">
                      {getPaneIcon(activeTierInfo.key)}
                      <span>{activeTierInfo.label}</span>
                    </div>
                    <div className="text-[10px] text-neutral-400 mt-0.5">{activeTierInfo.hint}</div>
                  </div>
                  <div className="flex-1 overflow-y-auto custom-scrollbar space-y-1.5 pr-1">
                    {geminiTierModels[activeTierInfo.key].map((m) => {
                      const isSelected = currentProvider === 'gemini' && currentModelId === m.id;
                      return (
                        <button
                          type="button"
                          key={m.id}
                          disabled={!geminiConfigured}
                          onClick={() => {
                            if (geminiConfigured) {
                              onSelectModel('gemini', m.id);
                              onClose();
                            }
                          }}
                          className={`flex h-[42px] w-full items-center justify-between rounded-xl px-3 text-left border transition-colors ${
                            isSelected
                              ? 'bg-sky-500/20 border-sky-400/45 text-white font-semibold'
                              : 'bg-white/[0.05] border-white/[0.06] text-neutral-100 hover:bg-white/[0.12] hover:border-white/20'
                          } ${!geminiConfigured ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}
                        >
                          <span className="text-[12.5px] font-medium truncate">{m.name}</span>
                          {isSelected && (
                            <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-400 text-slate-950">
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
