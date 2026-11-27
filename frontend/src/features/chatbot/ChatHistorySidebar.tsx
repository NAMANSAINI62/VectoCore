'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import {
  Check,
  Clock,
  MessageSquare,
  PanelLeftClose,
  Pencil,
  Search,
  Trash2,
  X,
} from 'lucide-react';

export type SidebarConversation = {
  id: string;
  title: string;
  selected_provider: string;
  selected_model: string;
  updated_at: string;
};

type TooltipAnchor = {
  item: SidebarConversation;
  rowTop: number;
  rowHeight: number;
  sidebarRight: number;
};

export type ChatHistorySidebarProps = {
  conversations: SidebarConversation[];
  activeId: string | null;
  currentCounterNumber: number;
  totalCount: number;
  isCollapsed: boolean;
  onCollapse: () => void;
  onOpenConversation: (id: string) => void;
  editingId: string | null;
  editingTitle: string;
  onStartEditing: (id: string, title: string) => void;
  onChangeEditingTitle: (title: string) => void;
  onCancelEditing: () => void;
  onRenameConversation: (id: string, nextTitle?: string) => void;
  onDeleteConversation: (id: string) => void;
};

function formatRelativeTime(isoDate: string): string {
  const ts = Date.parse(isoDate);
  if (!Number.isFinite(ts)) return '';
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return 'Just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function getTimeGroupLabel(isoDate: string): 'Today' | 'Yesterday' | 'Previous 7 Days' | 'Earlier' {
  const ts = Date.parse(isoDate);
  if (!Number.isFinite(ts)) return 'Earlier';
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const oneDay = 86_400_000;
  if (ts >= startOfToday) return 'Today';
  if (ts >= startOfToday - oneDay) return 'Yesterday';
  if (ts >= startOfToday - 7 * oneDay) return 'Previous 7 Days';
  return 'Earlier';
}

const TOOLTIP_CARD_ESTIMATED_HEIGHT = 138;

/**
 * Collapsible Chat History Sidebar featuring a grouped "Smart Hover Tooltip":
 * - Cold hover warms up gently (~200ms) so fast cursor passes don't flash noise
 * - Once active, moving across items glides a single shared tooltip card smoothly (0ms switch)
 * - Uses fixed viewport positioning + clamping so scrollable sidebar overflow never clips previews
 */
export const ChatHistorySidebar = memo(function ChatHistorySidebar({
  conversations,
  activeId,
  currentCounterNumber,
  totalCount,
  isCollapsed,
  onCollapse,
  onOpenConversation,
  editingId,
  editingTitle,
  onStartEditing,
  onChangeEditingTitle,
  onCancelEditing,
  onRenameConversation,
  onDeleteConversation,
}: ChatHistorySidebarProps) {
  const [filterQuery, setFilterQuery] = useState('');
  const [tooltip, setTooltip] = useState<TooltipAnchor | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [slideDir, setSlideDir] = useState<'up' | 'down'>('down');
  const [pendingAction, setPendingAction] = useState<
    | { type: 'delete'; item: SidebarConversation }
    | { type: 'edit'; item: SidebarConversation }
    | { type: 'rename'; item: SidebarConversation; nextTitle: string }
    | null
  >(null);

  const asideRef = useRef<HTMLElement>(null);
  const warmTimerRef = useRef<number | null>(null);
  const coolTimerRef = useRef<number | null>(null);
  const lastRowTopRef = useRef<number>(0);

  const clearTimers = useCallback(() => {
    if (warmTimerRef.current !== null) {
      window.clearTimeout(warmTimerRef.current);
      warmTimerRef.current = null;
    }
    if (coolTimerRef.current !== null) {
      window.clearTimeout(coolTimerRef.current);
      coolTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (isCollapsed || editingId !== null) {
      clearTimers();
      setIsVisible(false);
    }
  }, [isCollapsed, editingId, clearTimers]);

  useEffect(() => () => clearTimers(), [clearTimers]);

  const filteredConversations = useMemo(() => {
    const q = filterQuery.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((item) => item.title.toLowerCase().includes(q));
  }, [conversations, filterQuery]);

  const groupedConversations = useMemo(() => {
    const groups: Array<{ label: string; items: SidebarConversation[] }> = [];
    const byLabel = new Map<string, SidebarConversation[]>();
    for (const item of filteredConversations) {
      const label = getTimeGroupLabel(item.updated_at);
      let bucket = byLabel.get(label);
      if (!bucket) {
        bucket = [];
        byLabel.set(label, bucket);
        groups.push({ label, items: bucket });
      }
      bucket.push(item);
    }
    return groups;
  }, [filteredConversations]);

  const handleRowEnter = (item: SidebarConversation, rowEl: HTMLDivElement) => {
    if (isCollapsed || editingId === item.id) return;
    clearTimers();

    const rowRect = rowEl.getBoundingClientRect();
    const asideRect = asideRef.current?.getBoundingClientRect();
    const nextTop = rowRect.top;
    setSlideDir(nextTop >= lastRowTopRef.current ? 'down' : 'up');
    lastRowTopRef.current = nextTop;

    const anchor: TooltipAnchor = {
      item,
      rowTop: rowRect.top,
      rowHeight: rowRect.height,
      sidebarRight: asideRect ? asideRect.right : rowRect.right,
    };

    if (isVisible) {
      // Warm group already active: glide immediately to next row with zero delay
      setTooltip(anchor);
      return;
    }

    setTooltip(anchor);
    warmTimerRef.current = window.setTimeout(() => {
      setIsVisible(true);
      warmTimerRef.current = null;
    }, 200);
  };

  const handleListLeave = () => {
    clearTimers();
    coolTimerRef.current = window.setTimeout(() => {
      setIsVisible(false);
      coolTimerRef.current = null;
    }, 140);
  };

  // Compute viewport-clamped vertical coordinates for smooth shared-container glide
  const tooltipCoords = useMemo(() => {
    if (!tooltip || typeof window === 'undefined') {
      return { top: 0, left: 0, arrowOffset: 24 };
    }
    const rowCenterY = tooltip.rowTop + tooltip.rowHeight / 2;
    const minTop = 14;
    const maxTop = Math.max(minTop, window.innerHeight - TOOLTIP_CARD_ESTIMATED_HEIGHT - 14);
    const desiredTop = rowCenterY - TOOLTIP_CARD_ESTIMATED_HEIGHT / 2;
    const clampedTop = Math.min(maxTop, Math.max(minTop, desiredTop));
    const arrowOffset = Math.min(
      TOOLTIP_CARD_ESTIMATED_HEIGHT - 18,
      Math.max(18, rowCenterY - clampedTop),
    );
    return {
      top: clampedTop,
      left: tooltip.sidebarRight + 10,
      arrowOffset,
    };
  }, [tooltip]);

  return (
    <>
      <aside
        ref={asideRef}
        className={`relative z-10 flex shrink-0 flex-col border-r border-[var(--border)] bg-[var(--card)] transition-all duration-300 ease-in-out ${
          isCollapsed ? 'w-0 overflow-hidden opacity-0 border-r-0' : 'w-72 opacity-100'
        }`}
      >
        {/* Header: Counter + Collapse */}
        <div className="flex h-12 items-center justify-between border-b border-[var(--border)] px-3.5">
          <div className="flex items-center gap-2">
            <span className="flex h-7 min-w-[28px] px-2 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--muted)] text-xs font-semibold text-[var(--foreground)]">
              {currentCounterNumber}
            </span>
            <span className="text-xs text-[var(--muted-foreground)] font-medium">of {totalCount}</span>
          </div>

          <button
            type="button"
            onClick={onCollapse}
            title="Collapse sidebar"
            className="rounded-lg p-1.5 text-[var(--muted-foreground)] transition hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>

        {/* Compact Sidebar Search */}
        <div className="px-3 pt-2.5 pb-1.5">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--muted-foreground)]" />
            <input
              type="text"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              placeholder="Search chat history..."
              aria-label="Search chat history"
              className="h-8 w-full rounded-xl border border-[var(--border)] bg-[var(--muted)]/50 pl-8 pr-7 text-xs text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] outline-none transition focus:border-[var(--accent)] focus:bg-[var(--background)]"
            />
            {filterQuery && (
              <button
                type="button"
                onClick={() => setFilterQuery('')}
                aria-label="Clear chat search"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Scrollable Grouped Conversations List */}
        <div
          onMouseLeave={handleListLeave}
          onScroll={handleListLeave}
          className="custom-scrollbar flex-1 space-y-3 overflow-y-auto px-2.5 py-2"
        >
          {!filteredConversations.length && (
            <p className="px-3 py-8 text-center text-xs text-[var(--muted-foreground)]">
              {conversations.length ? 'No matching chats.' : 'No conversations yet.'}
            </p>
          )}

          {groupedConversations.map((group) => (
            <div key={group.label} className="space-y-1.5">
              <div className="px-2 pt-0.5 text-[11px] font-medium text-[var(--muted-foreground)]/85">
                {group.label}
              </div>

              {group.items.map((item) => {
                const isActive = activeId === item.id;
                const isHovered = isVisible && tooltip?.item.id === item.id;
                return (
                  <div
                    key={item.id}
                    onMouseEnter={(e) => handleRowEnter(item, e.currentTarget)}
                    onClick={() => onOpenConversation(item.id)}
                    className={`group relative flex items-center gap-2 rounded-xl border px-2.5 py-2 text-xs font-medium cursor-pointer transition-colors duration-100 focus-within:ring-2 focus-within:ring-[var(--accent)]/35 ${
                      isActive
                        ? 'bg-[var(--accent-soft)] border-[var(--accent)]/35 text-[var(--foreground)] shadow-sm ring-1 ring-[var(--accent)]/15'
                        : isHovered
                        ? 'bg-[var(--muted)] border-[var(--border)] text-[var(--foreground)] shadow-xs'
                        : 'bg-[var(--background)]/45 border-[var(--border)]/55 text-[var(--foreground)]/85 hover:bg-[var(--muted)] hover:border-[var(--border)] hover:text-[var(--foreground)]'
                    }`}
                  >
                    <div
                      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                        isActive
                          ? 'border-[var(--accent)]/30 bg-[var(--accent)]/15 text-[var(--accent)]'
                          : isHovered
                          ? 'border-[var(--border)] bg-[var(--card)] text-[var(--foreground)]'
                          : 'border-[var(--border)]/70 bg-[var(--card)]/70 text-[var(--muted-foreground)]'
                      }`}
                    >
                      <MessageSquare className="h-3 w-3" />
                    </div>
                    <button
                      type="button"
                      onClick={() => onOpenConversation(item.id)}
                      className={`min-w-0 flex-1 truncate text-left focus:outline-none focus-visible:outline-none ${
                        isActive ? 'font-semibold text-[var(--accent)]' : ''
                      }`}
                    >
                      {item.title}
                    </button>
                    <div
                      className={`flex shrink-0 items-center gap-1 transition-opacity duration-150 ${
                        isActive || isHovered
                          ? 'opacity-100'
                          : 'opacity-55 group-hover:opacity-100 group-focus-within:opacity-100'
                      }`}
                    >
                      <button
                        type="button"
                        aria-label={`Rename ${item.title}`}
                        title="Rename"
                        onClick={(e) => {
                          e.stopPropagation();
                          clearTimers();
                          setIsVisible(false);
                          onStartEditing(item.id, '');
                          setPendingAction({ type: 'edit', item });
                        }}
                        className="flex h-6 w-6 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--background)]/90 text-[var(--foreground)]/80 shadow-xs transition hover:border-[var(--accent)]/50 hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] focus:outline-none"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${item.title}`}
                        title="Delete"
                        onClick={(e) => {
                          e.stopPropagation();
                          clearTimers();
                          setIsVisible(false);
                          setPendingAction({ type: 'delete', item });
                        }}
                        className="flex h-6 w-6 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--background)]/90 text-rose-500/85 shadow-xs transition hover:border-rose-500/50 hover:bg-rose-500/15 hover:text-rose-600 focus:outline-none"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-[var(--border)] px-3.5 py-2.5 text-[11px] text-[var(--muted-foreground)]">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Account sync enabled
          </span>
          {filterQuery && (
            <span className="text-[10px] font-medium">
              {filteredConversations.length} match{filteredConversations.length === 1 ? '' : 'es'}
            </span>
          )}
        </div>
      </aside>

      {/* Shared Morphing Smart Hover Tooltip (single gliding container across sidebar rows) */}
      {!isCollapsed && tooltip && (
        <div
          aria-hidden={!isVisible}
          style={{
            top: 0,
            left: tooltipCoords.left,
            transform: `translate3d(${isVisible ? '0px' : '-6px'}, ${tooltipCoords.top}px, 0) scale(${
              isVisible ? 1 : 0.96
            })`,
            transition:
              'transform 220ms cubic-bezier(0.22, 1, 0.36, 1), opacity 150ms ease',
          }}
          className={`pointer-events-none fixed z-50 w-[290px] max-w-[calc(100vw-320px)] origin-left rounded-2xl border border-[var(--border)] bg-[var(--card)] p-3 text-[var(--foreground)] shadow-lg ${
            isVisible ? 'opacity-100' : 'opacity-0'
          }`}
        >
          {/* Gliding Left Arrow Beak */}
          <div
            style={{
              top: tooltipCoords.arrowOffset - 5,
              transition: 'top 150ms cubic-bezier(0.22, 1, 0.36, 1)',
            }}
            className="absolute -left-[6px] h-2.5 w-2.5 rotate-45 border-b border-l border-[var(--border)] bg-[var(--card)]"
          />

          {/* Directional Keyed Inner Content for Clean Micro-Crossfade */}
          <div
            key={tooltip.item.id}
            className={`space-y-2 animate-in fade-in duration-100 ${
              slideDir === 'down' ? 'slide-in-from-top-1' : 'slide-in-from-bottom-1'
            }`}
          >
            {/* Full Untruncated Prompt / Conversation Title */}
            <p className="text-[12.5px] font-medium leading-snug text-[var(--foreground)] line-clamp-4 break-words">
              {tooltip.item.title}
            </p>

            {/* Footer Micro-Status + Timestamp on Far Right */}
            <div className="flex items-center justify-between gap-2 border-t border-[var(--border)]/70 pt-1.5 text-[10px] text-[var(--muted-foreground)]">
              <div className="flex items-center gap-1.5 min-w-0">
                <span>{activeId === tooltip.item.id ? 'Currently open' : 'Click to open chat'}</span>
                {activeId === tooltip.item.id && (
                  <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 font-semibold text-[var(--accent)]">
                    Active
                  </span>
                )}
              </div>
              <span className="inline-flex shrink-0 items-center gap-1 font-medium text-[var(--muted-foreground)]">
                <Clock className="h-2.5 w-2.5" />
                {formatRelativeTime(tooltip.item.updated_at)}
              </span>
            </div>
          </div>
        </div>
      )}
      {/* Confirmation Dialog for Rename & Delete */}
      <Dialog
        open={pendingAction !== null}
        onClose={() => {
          setPendingAction(null);
          onCancelEditing();
        }}
        className="relative z-[100]"
      >
        <div className="fixed inset-0 bg-black/45 backdrop-blur-xs" aria-hidden="true" />
        <div className="fixed inset-0 flex items-center justify-center p-4">
          <DialogPanel className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 text-[var(--foreground)] shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            {pendingAction?.type === 'delete' && (
              <>
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-rose-500/30 bg-rose-500/10 text-rose-500">
                    <Trash2 className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <DialogTitle className="text-sm font-semibold text-[var(--foreground)]">
                      Delete conversation?
                    </DialogTitle>
                    <p className="mt-1 text-xs leading-relaxed text-[var(--muted-foreground)]">
                      This will permanently remove{' '}
                      <span className="font-semibold text-[var(--foreground)] break-words">
                        &ldquo;{pendingAction.item.title}&rdquo;
                      </span>{' '}
                      and its message history.
                    </p>
                  </div>
                </div>
                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setPendingAction(null)}
                    className="rounded-xl border border-[var(--border)] bg-[var(--muted)] px-3.5 py-1.5 text-xs font-medium text-[var(--foreground)] transition hover:bg-[var(--muted)]/80"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const targetId = pendingAction.item.id;
                      setPendingAction(null);
                      onDeleteConversation(targetId);
                    }}
                    className="rounded-xl bg-rose-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-rose-500"
                  >
                    Confirm Delete
                  </button>
                </div>
              </>
            )}

            {pendingAction?.type === 'edit' && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  const trimmed = editingTitle.trim();
                  if (!trimmed || trimmed === pendingAction.item.title) {
                    setPendingAction(null);
                    onCancelEditing();
                    return;
                  }
                  setPendingAction({ type: 'rename', item: pendingAction.item, nextTitle: trimmed });
                }}
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[var(--accent)]/30 bg-[var(--accent-soft)] text-[var(--accent)]">
                    <Pencil className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <DialogTitle className="text-sm font-semibold text-[var(--foreground)]">
                      Rename conversation
                    </DialogTitle>
                    <p className="mt-0.5 text-[11px] text-[var(--muted-foreground)]">
                      Edit the full title clearly below before confirming.
                    </p>
                  </div>
                </div>

                <div className="mt-4 space-y-3">
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--muted)]/45 p-2.5">
                    <div className="text-[11px] font-medium text-[var(--muted-foreground)]">
                      Current title
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-[var(--foreground)]/85 break-words whitespace-pre-wrap">
                      {pendingAction.item.title}
                    </p>
                  </div>

                  <div>
                    <div className="mb-1 flex items-center justify-between text-[11px] font-medium text-[var(--foreground)]">
                      <label htmlFor="rename-conversation-textarea">New title</label>
                      <span className="text-[10px] text-[var(--muted-foreground)]">
                        {editingTitle.length}/180
                      </span>
                    </div>
                    <textarea
                      id="rename-conversation-textarea"
                      autoFocus
                      rows={3}
                      maxLength={180}
                      value={editingTitle}
                      onChange={(e) => onChangeEditingTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          const trimmed = editingTitle.trim();
                          if (!trimmed || trimmed === pendingAction.item.title) {
                            setPendingAction(null);
                            onCancelEditing();
                            return;
                          }
                          setPendingAction({
                            type: 'rename',
                            item: pendingAction.item,
                            nextTitle: trimmed,
                          });
                        }
                      }}
                      className="w-full resize-none rounded-xl border border-[var(--accent)]/50 bg-[var(--background)] px-3 py-2 text-xs leading-relaxed text-[var(--foreground)] outline-none ring-2 ring-[var(--accent)]/15 focus:border-[var(--accent)]"
                      placeholder="Enter new conversation title..."
                    />
                  </div>
                </div>

                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPendingAction(null);
                      onCancelEditing();
                    }}
                    className="rounded-xl border border-[var(--border)] bg-[var(--muted)] px-3.5 py-1.5 text-xs font-medium text-[var(--foreground)] transition hover:bg-[var(--muted)]/80"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!editingTitle.trim() || editingTitle.trim() === pendingAction.item.title}
                    className="rounded-xl bg-[var(--accent)] px-3.5 py-1.5 text-xs font-semibold text-[var(--accent-foreground)] shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    Review &amp; Save
                  </button>
                </div>
              </form>
            )}

            {pendingAction?.type === 'rename' && (
              <>
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[var(--accent)]/30 bg-[var(--accent-soft)] text-[var(--accent)]">
                    <Check className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <DialogTitle className="text-sm font-semibold text-[var(--foreground)]">
                      Confirm rename?
                    </DialogTitle>
                    <div className="mt-2.5 space-y-2 rounded-xl border border-[var(--border)] bg-[var(--muted)]/50 p-3 text-xs leading-relaxed">
                      <div className="text-[var(--muted-foreground)]">
                        <span className="font-semibold">From:</span>{' '}
                        <span className="line-through opacity-75 break-words">{pendingAction.item.title}</span>
                      </div>
                      <div className="text-[var(--foreground)]">
                        <span className="font-semibold text-[var(--accent)]">To:</span>{' '}
                        <span className="font-semibold break-words">{pendingAction.nextTitle}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setPendingAction({ type: 'edit', item: pendingAction.item })}
                    className="rounded-xl border border-[var(--border)] bg-[var(--muted)] px-3.5 py-1.5 text-xs font-medium text-[var(--foreground)] transition hover:bg-[var(--muted)]/80"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const targetId = pendingAction.item.id;
                      const nextTitle = pendingAction.nextTitle;
                      setPendingAction(null);
                      onRenameConversation(targetId, nextTitle);
                    }}
                    className="rounded-xl bg-[var(--accent)] px-3.5 py-1.5 text-xs font-semibold text-[var(--accent-foreground)] shadow-sm transition hover:opacity-90"
                  >
                    Confirm Rename
                  </button>
                </div>
              </>
            )}
          </DialogPanel>
        </div>
      </Dialog>
    </>
  );
});
