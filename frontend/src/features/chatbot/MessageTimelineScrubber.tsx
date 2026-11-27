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
  modelId?: string | null;
  cacheLabel?: string | null;
};

export type MessageTimelineScrubberProps = {
  turns: TimelineTurn[];
  activeIndex: number;
  onSelectTurn: (turn: TimelineTurn) => void;
};

const IDLE_TICK_WIDTH = 10;
const ACTIVE_TICK_WIDTH = 15;
const HOVER_TICK_WIDTH = 20;
const PREVIEW_ESTIMATED_HEIGHT = 96;

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
 * Interactive Vertical Tick-Mark Conversation Scrubber:
 * - Left-aligned vertical ruler of calm turn ticks (simple highlight on hover/active, no wave bulge)
 * - Scrubbing displays a flat, minimal inline preview beside the hovered tick (no bubble/shadow)
 * - Clicking any tick or its preview jumps straight to that turn in the chat stream
 */
export const MessageTimelineScrubber = memo(function MessageTimelineScrubber({
  turns,
  activeIndex,
  onSelectTurn,
}: MessageTimelineScrubberProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
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

      if (forcedIndex === undefined) {
        const firstEl = tickRefs.current[0];
        const lastEl = tickRefs.current[turns.length - 1];
        if (firstEl && lastEl) {
          const topY = firstEl.getBoundingClientRect().top + firstEl.getBoundingClientRect().height / 2;
          const bottomY = lastEl.getBoundingClientRect().top + lastEl.getBoundingClientRect().height / 2;
          const span = Math.max(1, bottomY - topY);
          const ratio = Math.max(0, Math.min(1, (clientY - topY) / span));
          targetIdx = Math.round(ratio * (turns.length - 1));
        }
      }

      targetIdx = Math.max(0, Math.min(turns.length - 1, targetIdx));
      setHoveredIndex(targetIdx);

      const tickEl = tickRefs.current[targetIdx];
      if (tickEl) {
        const tickRect = tickEl.getBoundingClientRect();
        const centerRelTop = tickRect.top - railRect.top + tickRect.height / 2;
        const maxTop = Math.max(0, railRect.height - PREVIEW_ESTIMATED_HEIGHT + 8);
        const clampedTop = Math.max(-4, Math.min(maxTop, centerRelTop - PREVIEW_ESTIMATED_HEIGHT / 2));
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
      className="hidden sm:flex flex-col items-start justify-center absolute left-2.5 top-1/2 -translate-y-1/2 z-30 py-2 pr-3 select-none"
      data-scrubber-hit="1"
    >
      <div
        className="flex flex-col items-start max-h-[64vh] overflow-y-auto custom-scrollbar pr-1"
        data-scrubber-hit="1"
      >
        {turns.map((turn, idx) => {
          const isHovered = hoveredIndex === idx;
          const isCurrentScroll = activeIndex === idx;
          const widthPx = isHovered
            ? HOVER_TICK_WIDTH
            : isCurrentScroll
            ? ACTIVE_TICK_WIDTH
            : IDLE_TICK_WIDTH;
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
                className={`block rounded-full transition-[width,background-color,opacity] duration-150 ease-out ${
                  isHovered
                    ? 'h-[2.5px] bg-[var(--accent)] opacity-100'
                    : isHighlightedTick
                    ? 'h-[2px] bg-[var(--foreground)] opacity-85'
                    : 'h-[2px] bg-[var(--muted-foreground)] opacity-40 group-hover:opacity-75'
                }`}
              />
            </button>
          );
        })}
      </div>

      {/* Clean Flat Hover Preview (no index, no drop shadow/bubble, sits in left gutter) */}
      {hoveredTurn && (
        <div
          onMouseEnter={clearLeaveTimer}
          onMouseLeave={scheduleClose}
          style={{ top: `${cardTopPx}px` }}
          className="absolute left-[30px] z-40 w-[230px] sm:w-[256px] max-w-[calc(100vw-8rem)] transition-[top] duration-150 ease-out"
        >
          <button
            type="button"
            onClick={() => onSelectTurn(hoveredTurn)}
            className="w-full text-left rounded-[10px] border border-[var(--border)] bg-[var(--card)] px-3.5 py-2.5 text-[var(--card-foreground)] transition-colors hover:border-[var(--accent)] cursor-pointer"
          >
            <div className="text-[12.5px] font-semibold leading-snug text-[var(--foreground)] line-clamp-2 break-words">
              {hoveredTurn.prompt}
            </div>

            <p className="mt-1 text-[11.5px] leading-[1.45] text-[var(--muted-foreground)] line-clamp-2 break-words">
              {hoveredTurn.isStreaming && !hoveredTurn.responsePreview
                ? 'Generating response…'
                : hoveredTurn.responsePreview || 'Waiting for assistant response…'}
            </p>

            {(hoveredTurn.modelId || hoveredTurn.cacheLabel) && (
              <div className="mt-2 flex items-center gap-2.5 border-t border-[var(--border)] pt-1.5 text-[10.5px] text-[var(--muted-foreground)] truncate">
                {hoveredTurn.modelId && (
                  <span className="inline-flex items-center gap-1 truncate font-mono">
                    <Cpu className="h-3 w-3 shrink-0 opacity-70" />
                    <span className="truncate">{formatModelShortName(hoveredTurn.modelId)}</span>
                  </span>
                )}
                {hoveredTurn.cacheLabel && (
                  <span className="inline-flex items-center gap-1 truncate font-mono text-[var(--accent)]">
                    <Zap className="h-3 w-3 shrink-0" />
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
