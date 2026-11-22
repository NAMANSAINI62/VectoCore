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

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

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
        className={`mx-auto max-w-3xl relative rounded-[22px] border text-white transition-all duration-200 ease-out backdrop-blur-2xl ${
          isFocused || hasContent
            ? 'border-white/[0.22] shadow-xl shadow-black/60 ring-1 ring-white/10'
            : 'border-white/[0.12] shadow-lg shadow-black/45 hover:border-white/[0.16]'
        }`}
        style={{
          background: 'linear-gradient(180deg, rgba(32, 38, 48, 0.72) 0%, rgba(20, 24, 30, 0.82) 100%)',
          boxShadow: '0 16px 36px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
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
              placeholder="Ask anything..."
              className="h-6 w-full resize-none border-0 bg-transparent p-0 text-[14px] leading-6 text-neutral-100 placeholder:text-neutral-400 outline-none focus:ring-0 custom-scrollbar"
              style={{ minHeight: '24px', maxHeight: '120px' }}
            />
          </div>

          {/* Bottom Toolbar */}
          <div className="flex items-center justify-between pt-2 gap-2 border-t border-white/[0.08]">
            {/* Left: Model Selector Glass Pill */}
            <Popover className="relative">
              {({ open, close }) => (
                <>
                  <PopoverButton className="group flex h-8 items-center gap-2 rounded-xl px-3 text-xs font-medium text-neutral-200 border border-white/10 bg-black/30 backdrop-blur-md transition-all duration-150 hover:bg-black/40 hover:border-white/20 active:scale-95 shadow-sm focus:outline-none">
                    {provider === 'groq' ? (
                      <Zap className="h-3.5 w-3.5 text-neutral-200 shrink-0" />
                    ) : (
                      <Sparkles className="h-3.5 w-3.5 text-neutral-200 shrink-0" />
                    )}
                    <span className="font-semibold text-white max-w-[150px] sm:max-w-[240px] truncate">
                      {currentModel?.name ?? model}
                    </span>
                    <span className="text-[10px] text-neutral-400 px-1.5 py-0.5 rounded-md bg-white/5 border border-white/5">
                      {formatProviderLabel(provider)}
                    </span>
                    <ChevronDown
                      className={`h-3 w-3 text-neutral-400 transition-transform duration-200 ${
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
