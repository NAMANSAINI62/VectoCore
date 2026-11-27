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
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const segmentTimerRef = useRef<number | null>(null);
  const recognitionRef = useRef<{ stop: () => void; abort: () => void } | null>(null);
  const restartTimerRef = useRef<number | null>(null);
  const recordingRef = useRef(false);
  const recognitionFailedRef = useRef(false);
  const whisperUnavailableRef = useRef(false);
  const baseDraftRef = useRef('');
  const segmentsRef = useRef<string[]>([]);
  const carryoverLiveRef = useRef('');
  const liveFinalTextRef = useRef('');
  const liveInterimTextRef = useRef('');
  const liveStartIndexRef = useRef(0);
  const liveFinalCountRef = useRef(0);
  const uploadQueueRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    if (!recording) {
      setRecordingSeconds(0);
      return;
    }
    setRecordingSeconds(0);
    const id = window.setInterval(() => {
      setRecordingSeconds((prev) => prev + 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, [recording]);

  const clearTimers = () => {
    if (restartTimerRef.current !== null) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    if (segmentTimerRef.current !== null) {
      window.clearInterval(segmentTimerRef.current);
      segmentTimerRef.current = null;
    }
  };

  const syncDraft = () => {
    const combined = [
      baseDraftRef.current,
      ...segmentsRef.current,
      carryoverLiveRef.current,
      liveFinalTextRef.current,
      liveInterimTextRef.current,
    ]
      .filter(Boolean)
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 25000);
    setDraft(combined);
  };

  const polishFinalText = async (rawText: string) => {
    const cleanedRaw = rawText.trim();
    if (!cleanedRaw || cleanedRaw.length > 3500) return;
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
          segmentsRef.current = [cleaned];
          carryoverLiveRef.current = '';
          liveFinalTextRef.current = '';
          liveInterimTextRef.current = '';
          syncDraft();
        }
      }
    } catch {
      // Keep transcribed segments if polish fails
    } finally {
      setTranscribing(false);
      textareaRef.current?.focus();
    }
  };

  useEffect(() => {
    return () => {
      recordingRef.current = false;
      clearTimers();
      recognitionRef.current?.abort();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  const handleToggleRecording = async () => {
    setVoiceError(null);
    if (recording) {
      recordingRef.current = false;
      clearTimers();
      setRecording(false);
      recognitionRef.current?.stop();
      recognitionRef.current = null;

      const activeRecorder = mediaRecorderRef.current;
      if (activeRecorder && activeRecorder.state !== 'inactive') {
        activeRecorder.stop();
      } else {
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        window.setTimeout(() => {
          const tail = [carryoverLiveRef.current, liveFinalTextRef.current, liveInterimTextRef.current]
            .filter(Boolean)
            .join(' ')
            .trim();
          if (tail) {
            segmentsRef.current.push(tail);
            carryoverLiveRef.current = '';
            liveFinalTextRef.current = '';
            liveInterimTextRef.current = '';
            syncDraft();
          }
          const fullText = segmentsRef.current.filter(Boolean).join(' ').trim();
          if (fullText) {
            void polishFinalText(fullText);
          } else {
            setVoiceError('No speech detected. Try speaking closer to the microphone.');
          }
        }, 180);
      }
      return;
    }

    if (typeof window !== 'undefined' && !window.isSecureContext) {
      setVoiceError('INSECURE_ORIGIN');
      return;
    }

    clearTimers();
    baseDraftRef.current = draft.trim();
    segmentsRef.current = [];
    carryoverLiveRef.current = '';
    liveFinalTextRef.current = '';
    liveInterimTextRef.current = '';
    liveStartIndexRef.current = 0;
    liveFinalCountRef.current = 0;
    recognitionFailedRef.current = false;
    whisperUnavailableRef.current = false;
    uploadQueueRef.current = Promise.resolve();

    const startLiveSpeechPreview = () => {
      const SpeechRecognitionCtor =
        typeof window !== 'undefined'
          ? ((window as unknown as { SpeechRecognition?: new () => unknown; webkitSpeechRecognition?: new () => unknown })
              .SpeechRecognition ??
              (window as unknown as { webkitSpeechRecognition?: new () => unknown }).webkitSpeechRecognition)
          : undefined;
      if (!SpeechRecognitionCtor) return false;
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
        liveStartIndexRef.current = 0;
        liveFinalCountRef.current = 0;

        recognition.onresult = (event) => {
          const finalParts: string[] = [];
          const interimParts: string[] = [];
          let contiguousFinalEnd = liveStartIndexRef.current;
          let stillFinal = true;
          for (let i = liveStartIndexRef.current; i < event.results.length; i += 1) {
            const res = event.results[i];
            const piece = (res?.[0]?.transcript ?? '').trim();
            if (res?.isFinal) {
              if (piece) finalParts.push(piece);
              if (stillFinal) contiguousFinalEnd = i + 1;
            } else {
              stillFinal = false;
              if (piece) interimParts.push(piece);
            }
          }
          liveFinalCountRef.current = contiguousFinalEnd;
          liveFinalTextRef.current = finalParts.join(' ');
          liveInterimTextRef.current = interimParts.join(' ');
          syncDraft();
        };

        recognition.onerror = (ev) => {
          const code = ev.error ?? 'unknown';
          if (code === 'no-speech' || code === 'aborted') {
            return;
          }
          recognitionFailedRef.current = true;
          // MediaRecorder + live Whisper segments continue seamlessly in the background
          if (streamRef.current) {
            return;
          }
          if (code === 'not-allowed' || code === 'service-not-allowed') {
            setVoiceError('Microphone permission denied. Please allow microphone access in browser settings.');
          } else if (code === 'audio-capture') {
            setVoiceError('No microphone detected. Check your system microphone and try again.');
          } else if (code === 'network') {
            setVoiceError('Browser speech service unreachable. Try again or allow microphone access for Whisper.');
          } else {
            setVoiceError(`Voice recognition error (${code}). Please try again.`);
          }
        };

        recognition.onend = () => {
          recognitionRef.current = null;
          if (!recordingRef.current) return;
          // Preserve current live text without flicker before restarting SpeechRecognition
          const snapshot = [carryoverLiveRef.current, liveFinalTextRef.current, liveInterimTextRef.current]
            .filter(Boolean)
            .join(' ')
            .trim();
          if (whisperUnavailableRef.current) {
            if (snapshot) segmentsRef.current.push(snapshot);
            carryoverLiveRef.current = '';
          } else {
            carryoverLiveRef.current = snapshot;
          }
          liveFinalTextRef.current = '';
          liveInterimTextRef.current = '';
          syncDraft();

          if (!recognitionFailedRef.current) {
            if (restartTimerRef.current !== null) window.clearTimeout(restartTimerRef.current);
            restartTimerRef.current = window.setTimeout(() => {
              restartTimerRef.current = null;
              if (!recordingRef.current || recognitionFailedRef.current) return;
              if (!startLiveSpeechPreview()) {
                recognitionFailedRef.current = true;
              }
            }, 150);
            return;
          }
          if (!streamRef.current) {
            recordingRef.current = false;
            setRecording(false);
          }
        };

        recognition.start();
        recognitionRef.current = recognition;
        return true;
      } catch {
        return false;
      }
    };

    const enqueueAudioSegment = (blob: Blob, segIndex: number, isFinal: boolean) => {
      uploadQueueRef.current = uploadQueueRef.current.then(async () => {
        if (isFinal) setTranscribing(true);
        try {
          if (!whisperUnavailableRef.current && blob.size >= 1200) {
            try {
              const formData = new FormData();
              formData.append('file', blob, 'segment.webm');
              const res = await fetch('/api/v1/chat/transcribe?polish=false', {
                method: 'POST',
                credentials: 'include',
                body: formData,
              });
              if (res.ok) {
                const data = (await res.json()) as { transcript?: string };
                const text = (data.transcript ?? '').trim();
                if (text) {
                  // Refine this segment in-place so existing text never vanishes or jumps
                  segmentsRef.current[segIndex] = text;
                  syncDraft();
                }
                return;
              }
              if (res.status === 429 || res.status >= 500 || res.status === 503) {
                // Seamless mid-recording background fallback to Browser Web Speech API (zero stop/start)
                whisperUnavailableRef.current = true;
                if (recordingRef.current && !recognitionRef.current) {
                  recognitionFailedRef.current = false;
                  startLiveSpeechPreview();
                }
              }
            } catch {
              whisperUnavailableRef.current = true;
              if (recordingRef.current && !recognitionRef.current) {
                recognitionFailedRef.current = false;
                startLiveSpeechPreview();
              }
            }
          }
        } finally {
          if (isFinal) {
            setTranscribing(false);
            const fullText = segmentsRef.current.filter(Boolean).join(' ').trim();
            if (fullText) {
              await polishFinalText(fullText);
            } else {
              setVoiceError('No speech detected. Try speaking closer to the microphone.');
            }
          }
        }
      });
    };

    const preferredMime =
      typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';

    const startRecorderSegment = (stream: MediaStream) => {
      const segChunks: BlobPart[] = [];
      const recorder = preferredMime
        ? new MediaRecorder(stream, { mimeType: preferredMime })
        : new MediaRecorder(stream);

      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) segChunks.push(ev.data);
      };

      recorder.onstop = () => {
        const isFinal = !recordingRef.current;
        const placeholderText = isFinal
          ? [carryoverLiveRef.current, liveFinalTextRef.current, liveInterimTextRef.current]
              .filter(Boolean)
              .join(' ')
              .trim()
          : [carryoverLiveRef.current, liveFinalTextRef.current].filter(Boolean).join(' ').trim();

        // Keep live text in-place inside segmentsRef[segIndex] while Whisper refines it (zero flicker!)
        const segIndex = segmentsRef.current.length;
        segmentsRef.current.push(placeholderText);
        carryoverLiveRef.current = '';
        liveFinalTextRef.current = '';
        liveStartIndexRef.current = liveFinalCountRef.current;
        if (isFinal) {
          liveInterimTextRef.current = '';
        }
        syncDraft();

        const blob = new Blob(segChunks, { type: recorder.mimeType || 'audio/webm' });

        if (!isFinal && streamRef.current) {
          // Immediately open next live segment on the SAME open mic stream (zero audio gap!)
          startRecorderSegment(streamRef.current);
        } else {
          mediaRecorderRef.current = null;
          streamRef.current?.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
        }

        enqueueAudioSegment(blob, segIndex, isFinal);
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250);
    };

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      if (startLiveSpeechPreview()) {
        whisperUnavailableRef.current = true;
        recordingRef.current = true;
        setRecording(true);
      } else {
        setVoiceError('Voice input is not supported in this browser.');
      }
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      recordingRef.current = true;
      setRecording(true);
      startRecorderSegment(stream);
      startLiveSpeechPreview();

      // Rotate clean 15-second audio segments live while recording: normal prompts stay uncut,
      // and long 20,000+ char dictations stream continuously without stopping or flickering
      segmentTimerRef.current = window.setInterval(() => {
        if (!recordingRef.current) return;
        const active = mediaRecorderRef.current;
        if (active && active.state === 'recording') {
          active.stop();
        }
      }, 15000);
    } catch (err: unknown) {
      recordingRef.current = false;
      setRecording(false);
      const errName = err instanceof DOMException ? err.name : '';
      if (errName === 'NotAllowedError' || errName === 'PermissionDeniedError') {
        setVoiceError('Microphone permission denied. Allow microphone access for this site in browser settings.');
      } else if (errName === 'NotFoundError' || errName === 'DevicesNotFoundError') {
        setVoiceError('No microphone found. Please connect or enable a microphone and try again.');
      } else if (errName === 'NotReadableError' || errName === 'TrackStartError') {
        setVoiceError('Microphone is busy in another app. Close other apps using the mic and try again.');
      } else if (startLiveSpeechPreview()) {
        recordingRef.current = true;
        setRecording(true);
      } else {
        setVoiceError('Microphone access failed. Check browser permissions and make sure you are on http://localhost:4317.');
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
    const nextHeight = Math.min(el.scrollHeight, 180);
    el.style.height = `${Math.max(nextHeight, 24)}px`;
    if (recording) {
      el.scrollTop = el.scrollHeight;
    }
  }, [draft, recording]);

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
              maxLength={25000}
              rows={1}
              placeholder={
                recording
                  ? 'Listening... speak now (click ■ to finish)'
                  : transcribing
                    ? 'Transcribing your voice...'
                    : 'Ask anything...'
              }
              className="h-6 w-full resize-none border-0 bg-transparent p-0 text-[14px] leading-6 text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] outline-none focus:ring-0 custom-scrollbar"
              style={{ minHeight: '24px', maxHeight: '180px' }}
            />
            {voiceError && (
              <p className="mt-1 text-[11px] font-medium text-rose-600">
                {voiceError === 'INSECURE_ORIGIN' ? (
                  <>
                    Microphone is blocked on LAN HTTP URLs.{' '}
                    <a
                      href={`http://localhost:${typeof window !== 'undefined' && window.location.port ? window.location.port : '4317'}${typeof window !== 'undefined' ? window.location.pathname : '/playground'}`}
                      className="underline font-semibold hover:opacity-80"
                    >
                      Open on http://localhost:4317
                    </a>{' '}
                    to use voice input.
                  </>
                ) : (
                  voiceError
                )}
              </p>
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
              {recording ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-500/10 px-2 py-0.5 text-[11px] font-medium text-rose-600 tabular-nums">
                  <span className="h-1.5 w-1.5 rounded-full bg-rose-600 animate-pulse" />
                  {Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2, '0')}
                </span>
              ) : transcribing ? (
                <span className="text-[11px] font-medium text-[var(--muted-foreground)]">Refining...</span>
              ) : (
                <span className="hidden text-[10px] text-neutral-400 sm:inline-block">
                  {draft.length > 0 ? `${draft.length}/25000` : ''}
                </span>
              )}

              <button
                type="button"
                onClick={() => void handleToggleRecording()}
                disabled={sending || loading || transcribing}
                title={recording ? 'Stop recording' : transcribing ? 'Transcribing audio...' : 'Voice input (Speech-to-Text)'}
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
