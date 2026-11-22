'use client';

import { memo, useCallback, useMemo, useRef, useState } from 'react';
import { Cpu, Zap } from 'lucide-react';
import { formatModelShortName } from '@/components/charts/chartTheme';

export type TimelineTurn = {
  id: string;
  index: number;
  prompt: string;
  responsePreview: string;
  isStreaming?: boolean;
  isError?: boolean;
  modelId?: string | null;
  provider?: string | null;
  cacheLabel?: string | null;
};

export type MessageTimelineScrubberProps = {
  turns: TimelineTurn[];
  activeIndex: number;
  onSelectTurn: (turn: TimelineTurn) => void;
};

const IDLE_TICK_WIDTH = 10;
const ACTIVE_IDLE_WIDTH = 16;
const PEAK_TICK_WIDTH = 36;
const GAUSSIAN_SIGMA = 1.65;
const CARD_ESTIMATED_HEIGHT = 128;

/** Strip markdown syntax into crisp inline preview text (matching Codex/Pixlpin snippet flattening). */
export function flattenMarkdownSnippet(raw: string): string {
  if (!raw) return '';
  return raw
    .replace(/```[\s\S]*?```/g, (block) => {
      const inner = block.replace(/^```[^\n]*\n?/, '').replace(/```$/, '').trim();
      return inner ? inner.replace(/\s+/g, ' ') : '[code]';
    })
    .replace(/\|/g, ' · ')
    .replace(/^[#>*\-\d.]+\s+/gm, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_~]+/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Interactive Vertical Tick-Mark Conversation Scrubber (Codex / Claude style):
 * - Left-aligned vertical ruler of turn ticks extending rightward on hover
 * - Symmetric macOS-dock / Gaussian fisheye scaling across neighboring ticks (+/- 5)
 * - Active scroll-synced turn remains highlighted when unhovered
 * - Scrubbing glides a single shared floating preview card beside the focal tick
 * - Clicking any tick or its card jumps straight to that turn in the chat stream
 */
export const MessageTimelineScrubber = memo(function MessageTimelineScrubber({
  turns,
  activeIndex,
  onSelectTurn,
}: MessageTimelineScrubberProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [hoverFloatIndex, setHoverFloatIndex] = useState<number | null>(null);
  const [cardTopPx, setCardTopPx] = useState<number>(0);

  const railRef = useRef<HTMLDivElement>(null);
  const tickRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const leaveTimerRef = useRef<number | null>(null);

  const clearLeaveTimer = useCallback(() => {
    if (leaveTimerRef.current !== null) {
      window.clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    clearLeaveTimer();
    leaveTimerRef.current = window.setTimeout(() => {
      setHoveredIndex(null);
      setHoverFloatIndex(null);
      leaveTimerRef.current = null;
    }, 90);
  }, [clearLeaveTimer]);

  const updateHoverAtClientY = useCallback(
    (clientY: number, forcedIndex?: number) => {
      clearLeaveTimer();
      const rail = railRef.current;
      if (!rail || turns.length === 0) return;

      const railRect = rail.getBoundingClientRect();
      let targetIdx = forcedIndex ?? 0;
      let floatIdx = forcedIndex ?? 0;

      if (forcedIndex === undefined) {
        const firstEl = tickRefs.current[0];
        const lastEl = tickRefs.current[turns.length - 1];
        if (firstEl && lastEl) {
          const topY = firstEl.getBoundingClientRect().top + firstEl.getBoundingClientRect().height / 2;
          const bottomY = lastEl.getBoundingClientRect().top + lastEl.getBoundingClientRect().height / 2;
          const span = Math.max(1, bottomY - topY);
          const ratio = Math.max(0, Math.min(1, (clientY - topY) / span));
          floatIdx = ratio * (turns.length - 1);
          targetIdx = Math.round(floatIdx);
        }
      } else {
        floatIdx = forcedIndex;
      }

      targetIdx = Math.max(0, Math.min(turns.length - 1, targetIdx));
      setHoveredIndex(targetIdx);
      setHoverFloatIndex(floatIdx);

      const tickEl = tickRefs.current[targetIdx];
      if (tickEl) {
        const tickRect = tickEl.getBoundingClientRect();
        const centerRelTop = tickRect.top - railRect.top + tickRect.height / 2;
        const maxTop = Math.max(0, railRect.height - CARD_ESTIMATED_HEIGHT + 12);
        const clampedTop = Math.max(-8, Math.min(maxTop, centerRelTop - CARD_ESTIMATED_HEIGHT / 2));
        setCardTopPx(clampedTop);
      }
    },
    [clearLeaveTimer, turns.length],
  );

  const hoveredTurn = useMemo(
    () => (hoveredIndex !== null ? turns[hoveredIndex] ?? null : null),
    [hoveredIndex, turns],
  );

  if (turns.length === 0) return null;

  return (
    <div
      ref={railRef}
      onMouseLeave={scheduleClose}
      onMouseMove={(e) => {
        // Track vertical scrubbing smoothly anywhere along the left hit corridor
        if (e.target === e.currentTarget || (e.target as HTMLElement).dataset.scrubberHit === '1') {
          updateHoverAtClientY(e.clientY);
        }
      }}
      aria-label="Conversation message timeline scrubber"
      className="hidden sm:flex flex-col items-start justify-center absolute left-2.5 top-1/2 -translate-y-1/2 z-30 py-2 pr-4 select-none"
      data-scrubber-hit="1"
    >
      <div
        className="flex flex-col items-start max-h-[64vh] overflow-y-auto custom-scrollbar pr-1"
        data-scrubber-hit="1"
      >
        {turns.map((turn, idx) => {
          const isHovered = hoveredIndex === idx;
          const isCurrentScroll = activeIndex === idx;

          // Compute Gaussian dock-wave width when scrubbing
          let widthPx = isCurrentScroll ? ACTIVE_IDLE_WIDTH : IDLE_TICK_WIDTH;
          if (hoverFloatIndex !== null) {
            const dist = Math.abs(idx - hoverFloatIndex);
            const wave = Math.exp(-(dist * dist) / (2 * GAUSSIAN_SIGMA * GAUSSIAN_SIGMA));
            const dynamicWidth = Math.round(IDLE_TICK_WIDTH + (PEAK_TICK_WIDTH - IDLE_TICK_WIDTH) * wave);
            widthPx = isHovered ? PEAK_TICK_WIDTH : Math.max(widthPx, dynamicWidth);
          }

          const isHighlightedTick = isHovered || (hoveredIndex === null && isCurrentScroll);

          return (
            <button
              key={turn.id}
              ref={(el) => {
                tickRefs.current[idx] = el;
              }}
              type="button"
              data-scrubber-hit="1"
              aria-label={`Jump to turn ${idx + 1}: ${turn.prompt}`}
              onMouseEnter={(e) => updateHoverAtClientY(e.clientY, idx)}
              onFocus={() => updateHoverAtClientY(0, idx)}
              onClick={() => onSelectTurn(turn)}
              className="group flex items-center justify-start py-[3.5px] pr-2 text-left cursor-pointer focus:outline-none"
            >
              <span
                style={{ width: `${widthPx}px` }}
                className={`block rounded-full transition-[width,background-color,opacity] duration-100 ease-out ${
                  isHovered
                    ? 'h-[2.5px] bg-[var(--foreground)] opacity-100'
                    : isHighlightedTick
                    ? 'h-[2px] bg-[var(--foreground)] opacity-90'
                    : 'h-[2px] bg-[var(--muted-foreground)] opacity-45 group-hover:opacity-75'
                }`}
              />
            </button>
          );
        })}
      </div>

      {/* Single Shared Floating Preview Card */}
      {hoveredTurn && (
        <div
          onMouseEnter={clearLeaveTimer}
          onMouseLeave={scheduleClose}
          style={{ top: `${cardTopPx}px` }}
          className="absolute left-[48px] z-40 w-[340px] sm:w-[390px] max-w-[calc(100vw-8rem)] transition-[top] duration-100 ease-out"
        >
          <button
            type="button"
            onClick={() => onSelectTurn(hoveredTurn)}
            className="w-full text-left rounded-[14px] border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-[var(--card-foreground)] backdrop-blur-xl transition-transform active:scale-[0.99] hover:border-[var(--foreground)]/25 cursor-pointer"
            style={{
              boxShadow: '0 8px 28px rgba(0, 0, 0, 0.16), 0 1px 4px rgba(0, 0, 0, 0.08)',
            }}
          >
            {/* Line 1: Single-line bold user prompt title */}
            <div className="flex items-center justify-between gap-2">
              <div className="truncate text-[13.5px] font-semibold leading-snug text-[var(--foreground)]">
                {hoveredTurn.prompt}
              </div>
              <span className="shrink-0 font-mono text-[10px] text-[var(--muted-foreground)] opacity-75">
                #{hoveredTurn.index + 1}
              </span>
            </div>

            {/* Line 2–4: Assistant response snippet (max 3 lines) */}
            <p className="mt-1 text-[12.5px] leading-[1.45] text-[var(--muted-foreground)] line-clamp-3 break-words">
              {hoveredTurn.isStreaming && !hoveredTurn.responsePreview
                ? 'Generating response…'
                : hoveredTurn.responsePreview || 'Waiting for assistant response…'}
            </p>

            {/* Subtle metadata row (model + cache status, matching Codex file tags) */}
            {(hoveredTurn.modelId || hoveredTurn.cacheLabel) && (
              <div className="mt-2 flex items-center gap-3 text-[11px] text-[var(--muted-foreground)] opacity-85 truncate">
                {hoveredTurn.modelId && (
                  <span className="inline-flex items-center gap-1 truncate font-mono">
                    <Cpu className="h-3 w-3 shrink-0 opacity-75" />
                    <span className="truncate">{formatModelShortName(hoveredTurn.modelId)}</span>
                  </span>
                )}
                {hoveredTurn.cacheLabel && (
                  <span className="inline-flex items-center gap-1 truncate font-mono">
                    <Zap className="h-3 w-3 shrink-0 text-[var(--accent)]" />
                    <span className="truncate">{hoveredTurn.cacheLabel}</span>
                  </span>
                )}
              </div>
            )}
          </button>
        </div>
      )}
    </div>
  );
});
