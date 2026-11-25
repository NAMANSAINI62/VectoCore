'use client';

import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from 'react';
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react';
import {
  ArrowUp,
  ChevronDown,
  LoaderCircle,
  Mic,
  Sparkles,
  Square,
  Zap,
} from 'lucide-react';
import {
  formatProviderLabel,
  Model,
  ModelSelector,
  Provider,
} from './ModelSelector';

export type AIChatInputProps = {
  providers: Provider[];
  models: Model[];
  provider: string;
  model: string;
  onModelChange: (provider: string, modelId: string) => void;
  onSendMessage: (message: string) => void;
  onStop: () => void;
  sending: boolean;
  loading: boolean;
  disabled?: boolean;
};

export function AIChatInput({
  providers,
  models,
  provider,
  model,
  onModelChange,
  onSendMessage,
  onStop,
  sending,
  loading,
  disabled,
}: AIChatInputProps) {
  const [draft, setDraft] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const recognitionRef = useRef<{ stop: () => void; abort: () => void } | null>(null);
  const baseDraftRef = useRef('');
  const liveTranscriptRef = useRef('');
  const polishedSessionRef = useRef(false);

  const polishLiveTranscript = async (rawText: string) => {
    const cleanedRaw = rawText.trim();
    if (!cleanedRaw || polishedSessionRef.current) return;
    polishedSessionRef.current = true;
    setTranscribing(true);
    try {
      const polishRes = await fetch('/api/v1/chat/voice-polish', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: cleanedRaw }),
      });
      if (polishRes.ok) {
        const data = (await polishRes.json()) as { polished_text?: string };
        const cleaned = (data.polished_text ?? '').trim();
        if (cleaned) {
          const base = baseDraftRef.current;
          setDraft(base ? `${base} ${cleaned}` : cleaned);
        }
      }
    } catch {
      // Keep raw live transcript if polish fails
    } finally {
      setTranscribing(false);
      textareaRef.current?.focus();
    }
  };

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const handleToggleRecording = async () => {
    setVoiceError(null);
    if (recording) {
      recognitionRef.current?.stop();
      recognitionRef.current = null;
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      setRecording(false);
      if (liveTranscriptRef.current.trim()) {
        void polishLiveTranscript(liveTranscriptRef.current);
      }
      return;
    }

    baseDraftRef.current = draft.trim();
    liveTranscriptRef.current = '';
    polishedSessionRef.current = false;

    // 1. Start live word-by-word browser speech recognition when supported
    const SpeechRecognitionCtor =
      typeof window !== 'undefined'
        ? ((window as unknown as { SpeechRecognition?: new () => unknown; webkitSpeechRecognition?: new () => unknown })
            .SpeechRecognition ??
            (window as unknown as { webkitSpeechRecognition?: new () => unknown }).webkitSpeechRecognition)
        : undefined;

    let startedLiveRecognition = false;
    if (SpeechRecognitionCtor) {
      try {
        const recognition = new SpeechRecognitionCtor() as {
          continuous: boolean;
          interimResults: boolean;
          lang: string;
          onresult: ((ev: {
            results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
          }) => void) | null;
          onerror: ((ev: { error?: string }) => void) | null;
          onend: (() => void) | null;
          start: () => void;
          stop: () => void;
          abort: () => void;
        };
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-IN';

        recognition.onresult = (event) => {
          let finalText = '';
          let interimText = '';
          for (let i = 0; i < event.results.length; i += 1) {
            const result = event.results[i];
            const piece = result[0]?.transcript ?? '';
            if (result.isFinal) {
              finalText += piece;
            } else {
              interimText += piece;
            }
          }
          const combinedLive = `${finalText}${interimText}`.trim();
          liveTranscriptRef.current = combinedLive;
          const base = baseDraftRef.current;
          setDraft(base ? (combinedLive ? `${base} ${combinedLive}` : base) : combinedLive);
          textareaRef.current?.focus();
        };

        recognition.onerror = (ev) => {
          if (ev.error === 'not-allowed' || ev.error === 'service-not-allowed') {
            setVoiceError('Microphone permission denied. Please allow microphone access.');
          }
        };

        recognition.onend = () => {
          recognitionRef.current = null;
          setRecording(false);
          if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop();
          }
          if (liveTranscriptRef.current.trim()) {
            void polishLiveTranscript(liveTranscriptRef.current);
          }
        };

        recognition.start();
        recognitionRef.current = recognition;
        startedLiveRecognition = true;
      } catch {
        startedLiveRecognition = false;
      }
    }

    // 2. Also record audio for Groq Whisper fallback if live recognition didn't capture text
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      if (startedLiveRecognition) {
        setRecording(true);
      } else {
        setVoiceError('Voice input is not supported in this browser.');
      }
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';
      const recorder = preferredMime
        ? new MediaRecorder(stream, { mimeType: preferredMime })
        : new MediaRecorder(stream);

      chunksRef.current = [];
      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        // If live word-by-word recognition captured words, polish via shared helper (guarded against double-run)
        const rawLive = liveTranscriptRef.current.trim();
        if (rawLive) {
          await polishLiveTranscript(rawLive);
          return;
        }
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        if (blob.size === 0) return;
        setTranscribing(true);
        try {
          const formData = new FormData();
          formData.append('file', blob, 'recording.webm');
          const res = await fetch('/api/v1/chat/transcribe', {
            method: 'POST',
            credentials: 'include',
            body: formData,
          });
          if (res.ok) {
            const data = (await res.json()) as { transcript?: string };
            const text = (data.transcript ?? '').trim();
            if (text) {
              const base = baseDraftRef.current;
              setDraft(base ? `${base} ${text}` : text);
              textareaRef.current?.focus();
            } else {
              setVoiceError('No speech detected. Try speaking closer to the microphone.');
            }
          } else {
            let detail = `Transcription failed (${res.status})`;
            try {
              const err = (await res.json()) as { detail?: string };
              if (err?.detail) detail = err.detail;
            } catch {
              // Ignore parse errors
            }
            setVoiceError(detail);
          }
        } catch {
          setVoiceError('Could not reach transcription service.');
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start(250);
      setRecording(true);
    } catch {
      if (startedLiveRecognition) {
        setRecording(true);
      } else {
        setRecording(false);
        setVoiceError('Microphone access failed. Check browser permissions.');
      }
    }
  };

  // Auto-resize textarea smoothly as text expands
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    if (!draft) {
      el.style.height = '24px';
      return;
    }
    el.style.height = 'auto';
    const nextHeight = Math.min(el.scrollHeight, 120);
    el.style.height = `${Math.max(nextHeight, 24)}px`;
  }, [draft]);

  const activeProvider = providers.find((p) => p.id === provider);
  const currentModel =
    models.find((m) => m.id === model && m.provider === provider) ??
    models.find((m) => m.id === model);

  const handleSubmit = (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || sending || loading || disabled || !activeProvider?.configured) return;
    onSendMessage(text);
    setDraft('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const hasContent = draft.trim().length > 0;

  return (
    <div className="w-full relative px-4 pb-2 sm:px-6">
      {/* Translucent Glass Composer Container */}
      <div
        ref={containerRef}
        className={`mx-auto max-w-3xl relative rounded-2xl border transition-all duration-200 ease-out ${
          isFocused || hasContent
            ? 'border-[var(--accent)]/50 shadow-lg ring-1 ring-[var(--accent)]/20'
            : 'border-[var(--border)] shadow-md hover:border-[var(--accent)]/30'
        }`}
        style={{
          backgroundColor: 'var(--card)',
          color: 'var(--foreground)',
        }}
      >
        <form onSubmit={handleSubmit} className="flex flex-col p-2.5 sm:p-3">
          {/* Prompt textarea */}
          <div className="px-2 py-1">
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              onKeyDown={handleKeyDown}
              disabled={sending || loading}
              maxLength={12000}
              rows={1}
              placeholder={recording ? 'Listening... speak now' : 'Ask anything...'}
              className="h-6 w-full resize-none border-0 bg-transparent p-0 text-[14px] leading-6 text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] outline-none focus:ring-0 custom-scrollbar"
              style={{ minHeight: '24px', maxHeight: '120px' }}
            />
            {voiceError && (
              <p className="mt-1 text-[11px] font-medium text-rose-600">{voiceError}</p>
            )}
          </div>

          {/* Bottom Toolbar */}
          <div className="flex items-center justify-between pt-2 gap-2 border-t border-[var(--border)]">
            {/* Left: Model Selector Pill */}
            <Popover className="relative">
              {({ open, close }) => (
                <>
                  <PopoverButton className="group flex h-8 items-center gap-2 rounded-xl px-3 text-xs font-medium text-[var(--foreground)] border border-[var(--border)] bg-[var(--muted)]/60 transition-all duration-150 hover:bg-[var(--muted)] active:scale-95 shadow-sm focus:outline-none">
                    {provider === 'groq' ? (
                      <Zap className="h-3.5 w-3.5 text-[var(--accent)] shrink-0" />
                    ) : (
                      <Sparkles className="h-3.5 w-3.5 text-[var(--accent)] shrink-0" />
                    )}
                    <span className="font-semibold text-[var(--foreground)] max-w-[150px] sm:max-w-[240px] truncate">
                      {currentModel?.name ?? model}
                    </span>
                    <span className="text-[10px] text-[var(--muted-foreground)] px-1.5 py-0.5 rounded-md bg-[var(--card)] border border-[var(--border)]">
                      {formatProviderLabel(provider)}
                    </span>
                    <ChevronDown
                      className={`h-3 w-3 text-[var(--muted-foreground)] transition-transform duration-200 ${
                        open ? 'rotate-180' : ''
                      }`}
                    />
                  </PopoverButton>

                  <PopoverPanel className="absolute bottom-full left-0 pb-2 z-50 focus:outline-none">
                    <ModelSelector
                      isOpen={open}
                      onClose={close}
                      models={models}
                      providers={providers}
                      currentProvider={provider}
                      currentModelId={model}
                      onSelectModel={(newProvider, newModelId) => {
                        onModelChange(newProvider, newModelId);
                        close();
                      }}
                    />
                  </PopoverPanel>
                </>
              )}
            </Popover>

            {/* Right: Circular Send / Stop Action */}
            <div className="flex items-center gap-2">
              <span className="hidden text-[10px] text-neutral-400 sm:inline-block">
                {draft.length > 0 ? `${draft.length}/12000` : ''}
              </span>

              <button
                type="button"
                onClick={() => void handleToggleRecording()}
                disabled={sending || loading || transcribing}
                title={recording ? 'Stop recording' : transcribing ? 'Transcribing audio...' : 'Voice input (Whisper)'}
                aria-label={recording ? 'Stop recording' : 'Voice input'}
                className={`flex h-8 w-8 items-center justify-center rounded-full border transition-all active:scale-95 cursor-pointer ${
                  recording
                    ? 'border-rose-500 bg-rose-600 text-white animate-pulse'
                    : 'border-[var(--border)] bg-[var(--muted)]/70 text-[var(--foreground)] hover:bg-[var(--muted)]'
                } disabled:opacity-45 disabled:cursor-not-allowed`}
              >
                {transcribing ? (
                  <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                ) : recording ? (
                  <Square className="h-3 w-3 fill-current" />
                ) : (
                  <Mic className="h-3.5 w-3.5" />
                )}
              </button>

              {sending ? (
                <button
                  type="button"
                  onClick={onStop}
                  title="Stop generation"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-rose-600 text-white shadow-md hover:bg-rose-500 transition-all active:scale-95"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!hasContent || loading || !activeProvider?.configured}
                  title={!activeProvider?.configured ? 'Provider not configured' : 'Send prompt (Enter)'}
                  className={`flex h-8 w-8 items-center justify-center rounded-full transition-all active:scale-95 shadow-md ${
                    hasContent && activeProvider?.configured
                      ? 'bg-blue-600 text-white hover:bg-blue-500 shadow-blue-500/30'
                      : 'bg-white/10 text-neutral-400 cursor-not-allowed'
                  }`}
                >
                  {loading ? (
                    <LoaderCircle className="h-4 w-4 animate-spin text-white" />
                  ) : (
                    <ArrowUp className="h-4 w-4 stroke-[2.5]" />
                  )}
                </button>
              )}
            </div>
          </div>
        </form>
      </div>

      {/* Subtle footer label */}
      <div className="mx-auto mt-1.5 flex max-w-3xl flex-wrap items-center justify-between gap-2 px-3 text-[11px] text-[var(--muted-foreground)]">
        <span>Shift + Enter for new line · Enter to send</span>
        <span className="truncate">
          <span className="font-medium text-[var(--foreground)]">
            {formatProviderLabel(provider)}
          </span>{' '}
          / <span className="font-semibold text-[var(--foreground)]">{currentModel?.name ?? model}</span>
        </span>
      </div>
    </div>
  );
}
