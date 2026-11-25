'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertTriangle,
  Bookmark,
  Check,
  Copy,
  LoaderCircle,
  MessageSquarePlus,
  PanelLeftOpen,
  Pause,
  Sparkles,
  Square,
  ThumbsDown,
  ThumbsUp,
  Volume2,
  Zap,
} from 'lucide-react';
import { useDispatch } from 'react-redux';
import { ApiClient } from '@/lib/apiClient';
import { getSavedDefaultModel } from '@/lib/preferences';
import { cacheApi, useGetCacheStatsQuery } from '@/store/cacheApi';
import { AIChatInput } from './AIChatInput';
import { ChatHistorySidebar } from './ChatHistorySidebar';
import {
  API,
  consumeChatStream,
  type Conversation,
  type Message,
} from './chatStream';
import {
  flattenMarkdownSnippet,
  MessageTimelineScrubber,
  TimelineTurn,
} from './MessageTimelineScrubber';
import { Model, Provider } from './ModelSelector';

const MarkdownBody = memo(function MarkdownBody({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children, ...props }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            title={href}
            className="inline-flex items-center px-1 py-0.2 mx-0.5 rounded text-[11px] font-semibold underline decoration-dotted hover:opacity-80 transition-opacity"
            {...props}
          >
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
});

function ResponseLoadingBar({
  statusText,
  elapsedMs,
  expectedMs,
}: {
  statusText?: string;
  elapsedMs: number;
  expectedMs?: number;
}) {
  const hasBaseline = typeof expectedMs === 'number' && expectedMs > 0;
  const elapsedSec = (elapsedMs / 1000).toFixed(1);
  const expectedSec = hasBaseline ? (expectedMs / 1000).toFixed(1) : null;
  const remainingSec = hasBaseline ? Math.max(0, (expectedMs - elapsedMs) / 1000).toFixed(1) : null;
  const overBaseline = hasBaseline && elapsedMs > expectedMs;
  const pct = hasBaseline
    ? overBaseline
      ? 95
      : Math.min(94, Math.max(4, Math.round((elapsedMs / expectedMs) * 94)))
    : Math.min(90, Math.max(8, Math.round((elapsedMs / 5000) * 80)));

  return (
    <div className="w-full max-w-md space-y-2 rounded-xl border border-[var(--border)] bg-[var(--muted)]/50 px-3.5 py-2.5 text-[12px] text-[var(--muted-foreground)]">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
            <span className="absolute inset-0 rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)] animate-spin" />
            <Sparkles className="h-2.5 w-2.5 text-[var(--accent)] animate-pulse" />
          </span>
          <span className="truncate font-medium tracking-tight text-[var(--foreground)]">
            {statusText || 'Thinking & exploring…'}
          </span>
        </div>
        <span className="shrink-0 font-mono text-[11px] font-semibold tabular-nums text-[var(--foreground)]">
          {elapsedSec}s
          {hasBaseline && (
            <span className="font-normal text-[var(--muted-foreground)]">
              {overBaseline ? ` / ~${expectedSec}s avg` : ` · ~${remainingSec}s left`}
            </span>
          )}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--border)]">
        <div
          className={`h-full rounded-full bg-[var(--accent)] transition-all duration-150 ${overBaseline ? 'animate-pulse' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {hasBaseline && (
        <p className="text-[10.5px] text-[var(--muted-foreground)]">
          {overBaseline
            ? `Taking longer than this model's ${expectedSec}s historical average…`
            : `Estimated from this model's real ${expectedSec}s average latency`}
        </p>
      )}
    </div>
  );
}

export function Chatbot() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [provider, setProvider] = useState('groq');
  const [model, setModel] = useState('openai/gpt-oss-20b');
  const [loading, setLoading] = useState(true);
  const dispatch = useDispatch();
  const [sending, setSending] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const { data: cacheStats, refetch: refetchCacheStats } = useGetCacheStatsQuery({ days: 30 });
  const modelAvgLatencyMs = useMemo(() => {
    const map: Record<string, number> = {};
    for (const m of cacheStats?.model_usage ?? []) {
      if (m.avg_latency_ms > 0) map[m.model] = m.avg_latency_ms;
    }
    return map;
  }, [cacheStats]);

  useEffect(() => {
    if (!sending) {
      setElapsedMs(0);
      return;
    }
    const started = performance.now();
    setElapsedMs(0);
    const id = window.setInterval(() => {
      setElapsedMs(Math.round(performance.now() - started));
    }, 100);
    return () => window.clearInterval(id);
  }, [sending]);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [likedMap, setLikedMap] = useState<Record<string, 'up' | 'down'>>({});
  const [bookmarkedMap, setBookmarkedMap] = useState<Record<string, boolean>>({});
  const [ttsLoadingId, setTtsLoadingId] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  // Sidebar collapse toggle & timeline scrubber state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setIsSidebarCollapsed(true);
    }
  }, []);
  const [openingChat, setOpeningChat] = useState(false);
  const [activeTurnIndex, setActiveTurnIndex] = useState(0);
  const [highlightedTurnId, setHighlightedTurnId] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const openAbortRef = useRef<AbortController | null>(null);
  const openingIdRef = useRef<string | null>(null);
  const conversationCacheRef = useRef<Map<string, Conversation>>(new Map());
  const ttsCacheRef = useRef<Map<string, string[]>>(new Map());
  const ttsSessionRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamScrollRef = useRef<HTMLDivElement>(null);
  const turnRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const scrollRafRef = useRef<number | null>(null);

  const sendingRef = useRef(sending);
  sendingRef.current = sending;
  const editingIdRef = useRef(editingId);
  editingIdRef.current = editingId;
  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const syncInFlightRef = useRef(false);

  const refreshConversations = useCallback(async () => {
    const rows = await ApiClient.get<Conversation[]>(`${API}/conversations`);
    setConversations((prev) => {
      if (
        prev.length === rows.length &&
        prev.every((c, i) => c.id === rows[i].id && c.title === rows[i].title && c.updated_at === rows[i].updated_at)
      ) {
        return prev;
      }
      return rows;
    });
  }, []);

  useEffect(() => {
    const handleGlobalSync = async () => {
      if (syncInFlightRef.current || sendingRef.current || editingIdRef.current !== null) {
        return;
      }
      syncInFlightRef.current = true;
      try {
        await refreshConversations();
        const currentActiveId = activeIdRef.current;
        if (currentActiveId && !sendingRef.current) {
          const detail = await ApiClient.get<Conversation>(`${API}/conversations/${currentActiveId}`);
          if (sendingRef.current || activeIdRef.current !== currentActiveId) return;
          conversationCacheRef.current.set(currentActiveId, detail);
          const nextMsgs = detail.messages ?? [];
          if (nextMsgs.length !== messagesRef.current.length) {
            setMessages(nextMsgs);
          }
        }
      } catch {
        // Silent background sync: do not disrupt active typing with transient network errors
      } finally {
        syncInFlightRef.current = false;
      }
    };

    window.addEventListener('vectocore:sync', handleGlobalSync);
    return () => window.removeEventListener('vectocore:sync', handleGlobalSync);
  }, [refreshConversations]);

  useEffect(() => {
    let active = true;
    Promise.all([
      ApiClient.get<Provider[]>(`${API}/providers`),
      ApiClient.get<Model[]>(`${API}/models`),
      ApiClient.get<Conversation[]>(`${API}/conversations`),
    ])
      .then(([providerRows, modelRows, conversationRows]) => {
        if (!active) return;
        setProviders(providerRows);
        setModels(modelRows);
        setConversations(conversationRows);

        const savedDefault = getSavedDefaultModel();
        const savedProvider = savedDefault
          ? providerRows.find((item) => item.id === savedDefault.provider && item.configured && item.models.includes(savedDefault.modelId))
          : undefined;

        if (savedProvider && savedDefault) {
          setProvider(savedProvider.id);
          setModel(savedDefault.modelId);
        } else {
          const defaultProvider =
            providerRows.find((item) => item.id === 'groq' && item.configured) ??
            providerRows.find((item) => item.configured) ??
            providerRows[0];

          if (defaultProvider) {
            setProvider(defaultProvider.id);
            const firstModel = defaultProvider.models[0];
            if (firstModel) {
              setModel(firstModel);
            }
          }
        }
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : 'Could not connect to the chatbot service.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (sending) {
      bottomRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' });
    }
  }, [messages.length, sending]);

  useEffect(() => {
    if (!loading && !sending && activeId && messages.length > 0) {
      const raf = requestAnimationFrame(() => {
        if (streamScrollRef.current) {
          streamScrollRef.current.scrollTo({
            top: streamScrollRef.current.scrollHeight,
            behavior: 'smooth',
          });
        } else {
          bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
        }
      });
      return () => cancelAnimationFrame(raf);
    }
  }, [activeId, loading, messages.length]);

  const activeProvider = providers.find((item) => item.id === provider);

  // Dynamic calculation for "X of Y" counter
  const totalCount = conversations.length;
  const currentPositionIndex = activeId ? conversations.findIndex((c) => c.id === activeId) : -1;
  const currentCounterNumber = currentPositionIndex !== -1 ? currentPositionIndex + 1 : totalCount > 0 ? 1 : 0;

  const newConversation = useCallback(() => {
    abortRef.current?.abort();
    openAbortRef.current?.abort();
    openingIdRef.current = null;
    setOpeningChat(false);
    setActiveId(null);
    setMessages([]);
    setError(null);
    setSending(false);
  }, []);

  const openConversation = useCallback(async (id: string) => {
    abortRef.current?.abort();
    openAbortRef.current?.abort();
    const controller = new AbortController();
    openAbortRef.current = controller;
    openingIdRef.current = id;

    // Instant optimistic switch + instant cached messages if available
    setActiveId(id);
    setError(null);
    setSending(false);

    const cached = conversationCacheRef.current.get(id);
    if (cached) {
      setMessages(cached.messages ?? []);
      setProvider(cached.selected_provider);
      setModel(cached.selected_model);
      setOpeningChat(false);
    } else {
      setMessages([]);
      setOpeningChat(true);
    }

    try {
      const conversation = await ApiClient.get<Conversation>(`${API}/conversations/${id}`, controller.signal);
      if (openingIdRef.current !== id) return;
      conversationCacheRef.current.set(id, conversation);
      setMessages(conversation.messages ?? []);
      setProvider(conversation.selected_provider);
      setModel(conversation.selected_model);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') return;
      if (openingIdRef.current === id && !cached) {
        setError(cause instanceof Error ? cause.message : 'Could not open conversation.');
      }
    } finally {
      if (openingIdRef.current === id) {
        setOpeningChat(false);
      }
    }
  }, []);

  const handleSendMessage = async (text: string) => {
    if (!text || sending || !activeProvider?.configured) return;

    const assistantId = `pending-${Date.now()}`;
    const controller = new AbortController();
    abortRef.current = controller;
    const timeoutId = window.setTimeout(() => controller.abort('timeout_3m'), 180_000);

    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: 'user', content: text },
      { id: assistantId, role: 'assistant', content: '', status_text: 'Analyzing prompt & preparing workflow…' },
    ]);
    setSending(true);
    setError(null);

    let latestConversationId = activeId;
    try {
      await consumeChatStream(
        { conversation_id: activeId, message: text, provider, model },
        controller.signal,
        (evt) => {
          const { event: eventName, data } = evt;
          if (eventName === 'response.start' && typeof data.conversation_id === 'string' && data.conversation_id.length > 0) {
            latestConversationId = data.conversation_id;
            setActiveId(data.conversation_id);
          } else if (eventName === 'status.update' && typeof data.message === 'string') {
            const switchedFrom = typeof data.switched_from === 'string' ? data.switched_from : undefined;
            const activeModelLabel = typeof data.active_model === 'string' ? data.active_model : undefined;
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      status_text: data.message as string,
                      switched_note:
                        switchedFrom && activeModelLabel
                          ? `Auto-switched: ${switchedFrom} → ${activeModelLabel}`
                          : item.switched_note,
                    }
                  : item,
              ),
            );
          } else if (eventName === 'cache.telemetry') {
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      cache_telemetry: {
                        hit: Boolean(data.hit),
                        cache_type: String(data.cache_type ?? ''),
                        cache_source: typeof data.cache_source === 'string' ? data.cache_source : undefined,
                        effective_response_language:
                          typeof data.effective_response_language === 'string'
                            ? data.effective_response_language
                            : undefined,
                        similarity_score: typeof data.similarity_score === 'number' ? data.similarity_score : undefined,
                        lookup_latency_ms: typeof data.lookup_latency_ms === 'number' ? data.lookup_latency_ms : 0,
                        saved_tokens: typeof data.saved_tokens === 'number' ? data.saved_tokens : undefined,
                      },
                    }
                  : item,
              ),
            );
          } else if (eventName === 'content.delta' && typeof data.content === 'string') {
            setMessages((current) =>
              current.map((item) => (item.id === assistantId ? { ...item, content: item.content + data.content } : item)),
            );
          } else if (eventName === 'response.complete') {
            if (typeof data.message_id === 'string') {
              const switchedFrom = typeof data.switched_from === 'string' ? data.switched_from : undefined;
              const switchReason = typeof data.switch_reason === 'string' ? data.switch_reason : undefined;
              setMessages((current) =>
                current.map((item) =>
                  item.id === assistantId
                    ? {
                        ...item,
                        id: data.message_id as string,
                        provider: (data.provider as string) ?? provider,
                        model_id: (data.model as string) ?? model,
                        created_at: new Date().toISOString(),
                        status_text: undefined,
                        switched_note:
                          switchedFrom
                            ? `Auto-switched from ${switchedFrom}${switchReason ? ` (${switchReason})` : ''}`
                            : item.switched_note,
                      }
                    : item,
                ),
              );
            }
          } else if (eventName === 'response.error') {
            const detail =
              typeof data.detail === 'string' && data.detail.trim()
                ? data.detail
                : 'This model is currently experiencing high demand, so use different models.';
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantId
                  ? {
                      ...item,
                      is_error: item.content ? item.is_error : true,
                      status_text: undefined,
                      content: item.content || detail,
                    }
                  : item,
              ),
            );
          }
        },
      );
      await refreshConversations();
      void refetchCacheStats();
    } catch (cause) {
      const isTimeout3m = controller.signal.aborted && controller.signal.reason === 'timeout_3m';
      if (!isTimeout3m && cause instanceof DOMException && cause.name === 'AbortError') return;
      const errMsg = isTimeout3m
        ? "We're sorry — the selected model took longer than 3 minutes to respond, so the request was stopped automatically. Please try again or switch to a faster model."
        : cause instanceof Error
          ? cause.message
          : 'Message generation failed.';
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                is_error: item.content ? item.is_error : true,
                status_text: undefined,
                content: item.content || errMsg,
              }
            : item,
        ),
      );
    } finally {
      window.clearTimeout(timeoutId);
      setSending(false);
      abortRef.current = null;
      if (latestConversationId) {
        conversationCacheRef.current.delete(latestConversationId);
        setActiveId(latestConversationId);
      }
      dispatch(cacheApi.util.invalidateTags(['CacheEntries', 'CacheStats']));
      void refetchCacheStats();
    }
  };

  const stopGeneration = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSending(false);
  };

  const renameConversation = async (id: string, nextTitle?: string) => {
    const title = (nextTitle ?? editingTitle).trim();
    if (!title) return;
    try {
      const updated = await ApiClient.patch<Conversation>(`${API}/conversations/${id}`, { title });
      setConversations((current) => current.map((item) => (item.id === id ? { ...item, title: updated.title } : item)));
      setEditingId(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not rename conversation.');
    }
  };

  const deleteConversation = async (id: string) => {
    try {
      await ApiClient.delete(`${API}/conversations/${id}`);
      setConversations((current) => current.filter((item) => item.id !== id));
      if (activeId === id) newConversation();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete conversation.');
    }
  };

  const copyMessage = async (item: Message) => {
    try {
      await navigator.clipboard.writeText(item.content);
      setCopiedId(item.id);
      window.setTimeout(() => setCopiedId(null), 1600);
    } catch {
      setError('Could not copy message to clipboard.');
    }
  };

  const splitSpeechChunks = (text: string): string[] => {
    const capped = text.slice(0, 1000).trim();
    if (!capped) return [];
    const sentences = capped.split(/(?<=[.!?])\s+/).filter(Boolean);
    const chunks: string[] = [];
    let current = '';
    const maxLen = () => (chunks.length === 0 ? 220 : 400);
    for (const s of sentences) {
      if (current && current.length + 1 + s.length > maxLen()) {
        chunks.push(current.trim());
        current = s;
      } else {
        current = current ? `${current} ${s}` : s;
      }
    }
    if (current.trim()) chunks.push(current.trim());
    return chunks.length > 0 ? chunks : [capped.slice(0, 220)];
  };

  const fetchTtsUrl = async (chunk: string, voice: string): Promise<string> => {
    const res = await fetch(`${API}/chat/tts`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: chunk, voice }),
    });
    if (!res.ok) throw new Error(`TTS failed (${res.status})`);
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  };

  const toggleSpeech = async (item: Message) => {
    if (playingId === item.id) {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      stopSpeech();
      return;
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    stopSpeech();

    const cleanSpeechText = item.content
      .slice(0, 6000)
      .replace(/\[(\d+)\]\([^)]+\)/g, '')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/[*_`#>~-]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    const speakText = cleanSpeechText || item.content.slice(0, 6000);
    if (!speakText) return;

    const sessionId = ++ttsSessionRef.current;

    const playUrlsSequentially = (urls: string[], index: number) => {
      if (ttsSessionRef.current !== sessionId || index >= urls.length) {
        if (ttsSessionRef.current === sessionId) {
          setPlayingId(null);
          setPaused(false);
        }
        return;
      }
      const audio = new Audio(urls[index]);
      audioRef.current = audio;
      audio.onended = () => playUrlsSequentially(urls, index + 1);
      audio.onerror = () => {
        setPlayingId(null);
        setPaused(false);
      };
      setPlayingId(item.id);
      setPaused(false);
      void audio.play().catch(() => {
        setPlayingId(null);
        setPaused(false);
      });
    };

    const activeVoice = 'diana';
    const ttsCacheKey = `${item.id}:${activeVoice}`;
    const cachedUrls = ttsCacheRef.current.get(ttsCacheKey);
    if (cachedUrls && cachedUrls.length > 0) {
      playUrlsSequentially(cachedUrls, 0);
      return;
    }

    setTtsLoadingId(item.id);
    try {
      const chunks = splitSpeechChunks(speakText);
      const firstUrl = await fetchTtsUrl(chunks[0], activeVoice);
      if (ttsSessionRef.current !== sessionId) {
        URL.revokeObjectURL(firstUrl);
        return;
      }
      setTtsLoadingId(null);

      // Play chunk 1 immediately while prefetching remaining chunks in background
      const urls: string[] = [firstUrl];
      const remainingPromises = chunks.slice(1).map((c) => fetchTtsUrl(c, activeVoice));

      const playWithPrefetch = async (idx: number) => {
        if (ttsSessionRef.current !== sessionId) return;
        const audio = new Audio(urls[idx]);
        audioRef.current = audio;
        setPlayingId(item.id);
        setPaused(false);
        audio.onended = async () => {
          if (ttsSessionRef.current !== sessionId) return;
          const nextIdx = idx + 1;
          if (nextIdx >= chunks.length) {
            ttsCacheRef.current.set(ttsCacheKey, urls);
            setPlayingId(null);
            setPaused(false);
            return;
          }
          if (!urls[nextIdx]) {
            try {
              urls[nextIdx] = await remainingPromises[nextIdx - 1];
            } catch {
              setPlayingId(null);
              setPaused(false);
              return;
            }
          }
          void playWithPrefetch(nextIdx);
        };
        audio.onerror = () => {
          setPlayingId(null);
          setPaused(false);
        };
        await audio.play();
      };

      void Promise.all(remainingPromises)
        .then((rest) => {
          if (ttsSessionRef.current === sessionId) {
            rest.forEach((u, i) => {
              urls[i + 1] = u;
            });
            ttsCacheRef.current.set(ttsCacheKey, urls);
          }
        })
        .catch(() => {});

      await playWithPrefetch(0);
      return;
    } catch {
      // Fall back to browser speech synthesis if Groq TTS fails or quota is reached
    } finally {
      setTtsLoadingId(null);
    }

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(speakText);
      const voices = window.speechSynthesis.getVoices();
      const naturalVoice =
        voices.find((v) => /aria/i.test(v.name) && /^en/i.test(v.lang)) ||
        voices.find((v) => /neerja|jenny|female|zira|samantha|victoria|karen|moira|tessa/i.test(v.name) && /natural|online|google/i.test(v.name) && /^en/i.test(v.lang)) ||
        voices.find((v) => /natural|online|google/i.test(v.name) && /^en/i.test(v.lang)) ||
        voices.find((v) => /^en/i.test(v.lang));
      if (naturalVoice) utterance.voice = naturalVoice;
      utterance.volume = 1.0;
      utterance.rate = 0.95;
      utterance.pitch = 1.0;
      setPlayingId(item.id);
      setPaused(false);
      utterance.onend = () => {
        setPlayingId(null);
        setPaused(false);
      };
      window.speechSynthesis.speak(utterance);
    } else {
      setError('Text-to-speech is not supported in this browser.');
    }
  };

  const stopSpeech = () => {
    ttsSessionRef.current += 1;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setPlayingId(null);
    setPaused(false);
  };

  const handleModelChange = (newProvider: string, newModelId: string) => {
    setProvider(newProvider);
    setModel(newModelId);
  };

  // Build ordered prompt->response turns for the live timeline scrubber
  const timelineTurns = useMemo<TimelineTurn[]>(() => {
    const turns: TimelineTurn[] = [];
    for (let i = 0; i < messages.length; i += 1) {
      const msg = messages[i];
      if (msg.role !== 'user') continue;
      const next = messages[i + 1];
      const assistantMsg = next && next.role === 'assistant' ? next : null;
      const cacheLabel =
        assistantMsg?.cache_telemetry?.hit
          ? `${assistantMsg.cache_telemetry.cache_source ?? 'Hit'} · ${assistantMsg.cache_telemetry.lookup_latency_ms}ms`
          : null;
      turns.push({
        id: msg.id,
        index: turns.length,
        prompt: msg.content,
        responsePreview: assistantMsg
          ? flattenMarkdownSnippet(assistantMsg.content || assistantMsg.status_text || '')
          : '',
        isStreaming: Boolean(sending && assistantMsg && !assistantMsg.content),
        isError: Boolean(assistantMsg?.is_error),
        modelId: assistantMsg?.model_id ?? msg.model_id ?? null,
        provider: assistantMsg?.provider ?? msg.provider ?? null,
        cacheLabel,
      });
    }
    return turns;
  }, [messages, sending]);

  useEffect(() => {
    if (timelineTurns.length > 0) {
      setActiveTurnIndex((prev) => Math.min(prev, timelineTurns.length - 1));
    } else {
      setActiveTurnIndex(0);
    }
  }, [timelineTurns.length]);

  const scrollToTurn = useCallback((turn: TimelineTurn) => {
    const target = turnRefs.current[turn.id];
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    setActiveTurnIndex(turn.index);
    setHighlightedTurnId(turn.id);
    window.setTimeout(() => {
      setHighlightedTurnId((curr) => (curr === turn.id ? null : curr));
    }, 900);
  }, []);

  const handleStreamScroll = useCallback(() => {
    if (scrollRafRef.current !== null) return;
    scrollRafRef.current = window.requestAnimationFrame(() => {
      scrollRafRef.current = null;
      const container = streamScrollRef.current;
      if (!container || timelineTurns.length === 0) return;
      const containerTop = container.getBoundingClientRect().top;
      let bestIdx = 0;
      let bestScore = Number.POSITIVE_INFINITY;
      for (let i = 0; i < timelineTurns.length; i += 1) {
        const el = turnRefs.current[timelineTurns[i].id];
        if (!el) continue;
        const offset = el.getBoundingClientRect().top - containerTop;
        const score = Math.abs(offset - 24);
        if (score < bestScore) {
          bestScore = score;
          bestIdx = i;
        }
      }
      setActiveTurnIndex(bestIdx);
    });
  }, [timelineTurns]);

  const handleCollapseSidebar = useCallback(() => setIsSidebarCollapsed(true), []);
  const handleOpenConversation = useCallback((id: string) => {
    void openConversation(id);
  }, [openConversation]);
  const handleStartEditing = useCallback((id: string, title: string) => {
    setEditingId(id);
    setEditingTitle(title);
  }, []);
  const handleCancelEditing = useCallback(() => setEditingId(null), []);
  const handleRenameConversation = useCallback(
    (id: string, nextTitle?: string) => {
      void renameConversation(id, nextTitle);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editingTitle],
  );
  const handleDeleteConversation = useCallback(
    (id: string) => {
      conversationCacheRef.current.delete(id);
      void deleteConversation(id);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeId],
  );

  return (
    <div className="relative flex h-full w-full flex-1 overflow-hidden select-text bg-[var(--background)] text-[var(--foreground)] transition-colors duration-200">
      <ChatHistorySidebar
        conversations={conversations}
        activeId={activeId}
        currentCounterNumber={currentCounterNumber}
        totalCount={totalCount}
        isCollapsed={isSidebarCollapsed}
        onCollapse={handleCollapseSidebar}
        onOpenConversation={handleOpenConversation}
        editingId={editingId}
        editingTitle={editingTitle}
        onStartEditing={handleStartEditing}
        onChangeEditingTitle={setEditingTitle}
        onCancelEditing={handleCancelEditing}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
      />

      {/* MAIN CHAT AREA */}
      <section className="relative z-10 flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {/* Minimalist Top Bar: Expand button (if collapsed) + New Chat Button on right */}
        <header className="flex shrink-0 items-center justify-between h-12 border-b border-[var(--border)] bg-[var(--card)]/70 px-4 backdrop-blur-md sm:px-6">
          <div className="flex items-center gap-2">
            {isSidebarCollapsed && (
              <button
                type="button"
                onClick={() => setIsSidebarCollapsed(false)}
                title="Open history sidebar"
                className="flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs font-medium text-[var(--foreground)] transition hover:bg-[var(--muted)] shadow-xs"
              >
                <PanelLeftOpen className="h-4 w-4 text-[var(--accent)]" />
                <span>
                  {currentCounterNumber} of {totalCount}
                </span>
              </button>
            )}
          </div>

          {/* "+ New chat" Button at Top Right */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={newConversation}
              className="flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs font-medium text-[var(--foreground)] transition hover:bg-[var(--muted)] active:scale-95 shadow-xs"
            >
              <MessageSquarePlus className="h-4 w-4 text-[var(--accent)]" />
              <span>+ New chat</span>
            </button>
          </div>
        </header>

        {/* Global Warning Banner */}
        {(error || (activeProvider && !activeProvider.configured)) && (
          <div
            role="alert"
            className="mx-4 mt-2 rounded-2xl border border-rose-500/30 bg-rose-950/40 p-3.5 text-xs text-rose-200 backdrop-blur-xl sm:mx-6"
          >
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
              <div className="flex-1">
                {error ?? `The ${provider} provider is not configured. Ask an administrator to add its backend API key.`}
              </div>
              {error && (
                <button
                  type="button"
                  onClick={() => setError(null)}
                  className="font-semibold underline hover:text-white"
                >
                  Dismiss
                </button>
              )}
            </div>
          </div>
        )}

        {/* MESSAGE STREAM + TIMELINE SCRUBBER */}
        <div className="relative flex min-h-0 flex-1 flex-col">
          <MessageTimelineScrubber
            turns={timelineTurns}
            activeIndex={activeTurnIndex}
            onSelectTurn={scrollToTurn}
          />
          <div
            ref={streamScrollRef}
            onScroll={handleStreamScroll}
            className="custom-scrollbar flex-1 overflow-y-auto px-4 py-3 sm:pl-14 sm:pr-8"
          >
          {(loading || (openingChat && !messages.length)) && (
            <div className="flex h-full items-center justify-center text-sm text-[var(--muted-foreground)]">
              <LoaderCircle className="mr-2 h-4 w-4 animate-spin text-[var(--accent)]" />
              {loading ? 'Connecting to workspace models…' : 'Opening conversation…'}
            </div>
          )}

          {!loading && !openingChat && !messages.length && (
            <div className="mx-auto flex h-full max-w-xl flex-col items-center justify-center text-center">
              <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--card)] text-[var(--accent)] shadow-sm">
                <Sparkles className="h-5 w-5" />
              </div>
              <h2 className="mt-3 text-xl font-semibold tracking-tight text-[var(--foreground)] sm:text-2xl">
                What is on your mind?
              </h2>
            </div>
          )}

          {messages.length > 0 && (
          <div className="mx-auto max-w-3xl space-y-6 py-2">
            {messages.map((item) => (
              <div
                key={item.id}
                ref={(el) => {
                  if (item.role === 'user') {
                    turnRefs.current[item.id] = el;
                  }
                }}
                className={`w-full space-y-4 scroll-mt-4 rounded-2xl transition-shadow duration-300 ${
                  highlightedTurnId === item.id ? 'ring-2 ring-[var(--accent)]/40 ring-offset-4 ring-offset-transparent' : ''
                }`}
              >
                {/* 1. USER MESSAGE */}
                {item.role === 'user' && (
                  <div className="flex items-start justify-end gap-2.5">
                    <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-[var(--accent)] px-4 py-2.5 text-xs sm:text-[13px] leading-relaxed text-[var(--accent-foreground)] shadow-sm">
                      <p className="whitespace-pre-wrap">{item.content}</p>
                    </div>
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] border border-[var(--border)] text-[10px] font-semibold text-[var(--accent)]">
                      U
                    </div>
                  </div>
                )}

                {/* 2. ASSISTANT RESPONSE */}
                {item.role === 'assistant' && (
                  <div className="flex flex-col items-start gap-2.5 max-w-full rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 sm:p-5 shadow-xs">
                    {/* Assistant Pill Tag & Cache Status Tag */}
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--muted)] px-3 py-1 text-[11px] font-medium text-[var(--foreground)]">
                        <Sparkles className="h-3 w-3 text-[var(--accent)]" />
                        <span>Assistant</span>
                      </div>
                      {item.switched_note && (
                        <div className="inline-flex items-center gap-1 rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-0.5 text-[10.5px] font-medium text-sky-300">
                          <span>{item.switched_note}</span>
                        </div>
                      )}
                      {item.cache_telemetry && item.cache_telemetry.hit && (
                        <div className="inline-flex items-center gap-1 rounded-full bg-[var(--hit-bg)] px-2.5 py-0.5 text-[11px] font-semibold text-[var(--hit-text)]">
                          <Zap className="h-3 w-3" />
                          <span>
                            {item.cache_telemetry.cache_source ?? 'Hit'} · {item.cache_telemetry.lookup_latency_ms}ms
                          </span>
                        </div>
                      )}
                      {item.cache_telemetry?.effective_response_language && (
                        <div className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--muted)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
                          <span>{item.cache_telemetry.effective_response_language}</span>
                        </div>
                      )}
                    </div>

                    {/* Markdown Body */}
                    <div className="w-full text-xs sm:text-[13px] leading-relaxed text-[var(--foreground)] break-words [&_a]:text-[var(--accent)] [&_a]:underline [&_blockquote]:my-3 [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--border)] [&_blockquote]:pl-3 [&_code]:rounded [&_code]:bg-[var(--code-bg)] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-xs [&_code]:text-[var(--code-text)] [&_h1]:my-3 [&_h1]:text-lg [&_h1]:font-semibold [&_h1]:text-[var(--foreground)] [&_h2]:my-2.5 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-[var(--foreground)] [&_li]:ml-5 [&_li]:list-disc [&_ol_li]:list-decimal [&_p]:mb-2.5 [&_p:last-child]:mb-0 [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-[var(--border)] [&_pre]:bg-[var(--code-bg)] [&_pre]:p-3.5 [&_pre]:text-[var(--code-text)] [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_table]:my-3 [&_td]:border [&_td]:border-[var(--border)] [&_td]:px-2.5 [&_td]:py-1 [&_th]:border [&_th]:border-[var(--border)] [&_th]:bg-[var(--muted)] [&_th]:px-2.5 [&_th]:py-1 [&_ul]:my-2.5">
                      {item.content ? (
                        <MarkdownBody content={item.content} />
                      ) : sending ? (
                        <ResponseLoadingBar
                          statusText={item.status_text}
                          elapsedMs={elapsedMs}
                          expectedMs={modelAvgLatencyMs[model]}
                        />
                      ) : null}
                    </div>

                    {/* Action Bar (Copy, Like, Dislike, Bookmark, TTS) */}
                    {item.content && !item.is_error && (
                      <div className="flex items-center gap-1 pt-1 text-[var(--muted-foreground)]">
                        {/* Copy */}
                        <button
                          type="button"
                          onClick={() => void copyMessage(item)}
                          title="Copy text"
                          className="rounded-lg p-1.5 transition hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                        >
                          {copiedId === item.id ? (
                            <Check className="h-3.5 w-3.5 text-emerald-500" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>

                        {/* Thumbs Up (Like) */}
                        <button
                          type="button"
                          onClick={() =>
                            setLikedMap((prev) => ({
                              ...prev,
                              [item.id]: prev[item.id] === 'up' ? undefined! : 'up',
                            }))
                          }
                          title="Good response"
                          className={`rounded-lg p-1.5 transition hover:bg-[var(--muted)] ${
                            likedMap[item.id] === 'up' ? 'text-[var(--accent)]' : 'hover:text-[var(--foreground)]'
                          }`}
                        >
                          <ThumbsUp className="h-3.5 w-3.5" />
                        </button>

                        {/* Thumbs Down (Dislike) */}
                        <button
                          type="button"
                          onClick={() =>
                            setLikedMap((prev) => ({
                              ...prev,
                              [item.id]: prev[item.id] === 'down' ? undefined! : 'down',
                            }))
                          }
                          title="Bad response"
                          className={`rounded-lg p-1.5 transition hover:bg-[var(--muted)] ${
                            likedMap[item.id] === 'down' ? 'text-rose-500' : 'hover:text-[var(--foreground)]'
                          }`}
                        >
                          <ThumbsDown className="h-3.5 w-3.5" />
                        </button>

                        {/* Bookmark */}
                        <button
                          type="button"
                          onClick={() =>
                            setBookmarkedMap((prev) => ({
                              ...prev,
                              [item.id]: !prev[item.id],
                            }))
                          }
                          title="Save response"
                          className={`rounded-lg p-1.5 transition hover:bg-[var(--muted)] ${
                            bookmarkedMap[item.id] ? 'text-amber-500 fill-amber-500' : 'hover:text-[var(--foreground)]'
                          }`}
                        >
                          <Bookmark className={`h-3.5 w-3.5 ${bookmarkedMap[item.id] ? 'fill-current' : ''}`} />
                        </button>

                        {/* Read Aloud TTS */}
                        <button
                          type="button"
                          disabled={ttsLoadingId === item.id}
                          onClick={() => void toggleSpeech(item)}
                          title={playingId === item.id ? (paused ? 'Resume audio' : 'Pause audio') : 'Read aloud'}
                          className="rounded-lg p-1.5 transition hover:bg-[var(--muted)] hover:text-[var(--foreground)] disabled:opacity-50"
                        >
                          {ttsLoadingId === item.id ? (
                            <LoaderCircle className="h-3.5 w-3.5 animate-spin text-[var(--accent)]" />
                          ) : playingId === item.id && !paused ? (
                            <Pause className="h-3.5 w-3.5 text-[var(--accent)]" />
                          ) : (
                            <Volume2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
          )}
          </div>
        </div>

        {/* BOTTOM CHAT COMPOSER: Matching Floating Glass Panel from Screenshot */}
        <div className="shrink-0 pt-1">
          <AIChatInput
            providers={providers}
            models={models}
            provider={provider}
            model={model}
            onModelChange={handleModelChange}
            onSendMessage={handleSendMessage}
            onStop={stopGeneration}
            sending={sending}
            loading={loading}
          />
        </div>
      </section>
    </div>
  );
}
