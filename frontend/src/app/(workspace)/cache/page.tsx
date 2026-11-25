'use client';

import React, { useMemo, useState } from 'react';
import { Dialog, DialogPanel } from '@headlessui/react';
import {
  useGetCacheEntriesQuery,
  useDeleteCacheEntryMutation,
  CacheEntry,
} from '@/store/cacheApi';
import { useAppSelector } from '@/store';
import { isIsoDateInRange } from '@/store/dateRangeSlice';
import {
  Check,
  Copy,
  Database,
  Eye,
  Globe,
  Layers,
  RefreshCw,
  Search,
  Trash2,
  X,
  Zap,
} from 'lucide-react';
import {
  getLanguageLabel,
  QUICK_LANGUAGE_CODES,
  SUPPORTED_LANGUAGES,
} from '@/lib/languages';

export default function CachePage() {
  const [search, setSearch] = useState('');
  const [language, setLanguage] = useState('');
  const [page, setPage] = useState(1);
  const [selectedEntry, setSelectedEntry] = useState<CacheEntry | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<CacheEntry | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [refreshSpin, setRefreshSpin] = useState(false);

  const quickLanguages = useMemo(
    () => SUPPORTED_LANGUAGES.filter((item) => QUICK_LANGUAGE_CODES.includes(item.code)),
    []
  );

  const selectLanguage = (code: string) => {
    setLanguage(code);
    setPage(1);
  };

  const { data, isLoading, isFetching, refetch } = useGetCacheEntriesQuery(
    {
      page,
      pageSize: 15,
      search: search.trim() || undefined,
      language: language || undefined,
    },
    {
      pollingInterval: 30000,
      skipPollingIfUnfocused: true,
      refetchOnMountOrArgChange: 15,
    }
  );

  const [deleteEntry, { isLoading: isDeleting }] = useDeleteCacheEntryMutation();

  const handleRefresh = async () => {
    setRefreshSpin(true);
    await refetch();
    setTimeout(() => setRefreshSpin(false), 450);
  };

  const handleConfirmDelete = async () => {
    if (!confirmDelete) return;
    await deleteEntry(confirmDelete.id);
    if (selectedEntry?.id === confirmDelete.id) {
      setSelectedEntry(null);
    }
    setConfirmDelete(null);
  };

  const handleCopyResponse = async (entry: CacheEntry) => {
    try {
      await navigator.clipboard.writeText(entry.response);
      setCopiedId(entry.id);
      setTimeout(() => setCopiedId((prev) => (prev === entry.id ? null : prev)), 1500);
    } catch {
      // Clipboard unavailable
    }
  };

  const { selectedDays, appliedCustom } = useAppSelector((state) => state.dateRange);

  const filteredItems = useMemo(
    () =>
      (data?.items ?? []).filter((item) =>
        isIsoDateInRange(item.created_at, selectedDays, appliedCustom),
      ),
    [data?.items, selectedDays, appliedCustom],
  );

  const pageMetrics = useMemo(() => {
    const items = filteredItems;
    let hits = 0;
    let saved = 0;
    for (const item of items) {
      hits += item.hit_count;
      saved += item.hit_count * (item.input_tokens + item.output_tokens);
    }
    return { count: items.length, hits, saved };
  }, [filteredItems]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1
            className="text-2xl font-medium tracking-tight flex items-center gap-2"
            style={{ color: 'var(--foreground)' }}
          >
            <Database className="w-5 h-5" style={{ color: 'var(--accent)' }} />
            Semantic Cache Explorer
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
            Inspect, filter, and invalidate stored prompt-response vectors across languages and models.
          </p>
        </div>
      </div>

      {/* 4-Column Summary KPI Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div
          className="rounded-xl border p-4 flex flex-col justify-between"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Stored Entries
            </span>
            <Database className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {isLoading ? '—' : (data?.total ?? 0).toLocaleString()}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted-foreground)' }}>
            Showing {pageMetrics.count} on page {data?.page ?? 1}
          </div>
        </div>

        <div
          className="rounded-xl border p-4 flex flex-col justify-between"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Page Reuse Hits
            </span>
            <Zap className="w-4 h-4" style={{ color: 'var(--hit-text)' }} />
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {isLoading ? '—' : pageMetrics.hits.toLocaleString()}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted-foreground)' }}>
            Cumulative hits on visible entries
          </div>
        </div>

        <div
          className="rounded-xl border p-4 flex flex-col justify-between"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Page Tokens Saved
            </span>
            <Layers className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          </div>
          <div
            className="text-2xl font-medium tracking-tight mt-2 tabular-nums"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {isLoading ? '—' : pageMetrics.saved.toLocaleString()}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted-foreground)' }}>
            Input + output tokens avoided
          </div>
        </div>

        <div
          className="rounded-xl border p-4 flex flex-col justify-between"
          style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--muted-foreground)' }}
            >
              Language Scope
            </span>
            <Globe className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          </div>
          <div
            className="text-xl font-medium mt-2 truncate"
            style={{ color: 'var(--stat-number, var(--foreground))' }}
          >
            {language ? getLanguageLabel(language) : 'All Languages'}
          </div>
          <div className="text-[11px] mt-1" style={{ color: 'var(--muted-foreground)' }}>
            {quickLanguages.length} quick filters available
          </div>
        </div>
      </div>

      {/* Search & Language Filter Toolbar */}
      <div
        className="rounded-xl border p-3 flex flex-col xl:flex-row xl:items-center gap-3"
        style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
      >
        <div className="relative flex-1">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: 'var(--muted-foreground)' }}
          />
          <input
            type="text"
            placeholder="Search cached queries or responses..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="w-full pl-9 pr-8 py-2 text-xs sm:text-sm rounded-lg border focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            style={{
              backgroundColor: 'var(--background)',
              borderColor: 'var(--border)',
              color: 'var(--foreground)',
            }}
          />
          {search && (
            <button
              type="button"
              onClick={() => {
                setSearch('');
                setPage(1);
              }}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-[var(--muted)]"
              style={{ color: 'var(--muted-foreground)' }}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div
          role="group"
          aria-label="Quick language filter"
          className="inline-flex flex-wrap items-center gap-1 p-1 rounded-lg border"
          style={{ backgroundColor: 'var(--background)', borderColor: 'var(--border)' }}
        >
          <button
            type="button"
            onClick={() => selectLanguage('')}
            aria-pressed={language === ''}
            className="px-2.5 py-1 rounded-md text-xs font-medium transition cursor-pointer"
            style={
              language === ''
                ? { backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }
                : { color: 'var(--muted-foreground)' }
            }
          >
            All
          </button>
          {quickLanguages.map((opt) => {
            const active = language === opt.code;
            return (
              <button
                key={opt.code}
                type="button"
                onClick={() => selectLanguage(opt.code)}
                aria-pressed={active}
                className="px-2.5 py-1 rounded-md text-xs font-medium transition cursor-pointer"
                style={
                  active
                    ? { backgroundColor: 'var(--accent)', color: 'var(--accent-foreground)' }
                    : { color: 'var(--muted-foreground)' }
                }
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Entries Table */}
      <div
        className="rounded-xl border overflow-hidden"
        style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
      >
        {isLoading ? (
          <div className="p-12 text-center text-xs" style={{ color: 'var(--muted-foreground)' }}>
            Loading cache entries...
          </div>
        ) : !data || filteredItems.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <Database className="w-8 h-8 mx-auto" style={{ color: 'var(--muted-foreground)' }} />
            <h3 className="text-sm font-semibold" style={{ color: 'var(--foreground)' }}>
              No Cache Entries Found
            </h3>
            <p className="text-xs max-w-sm mx-auto" style={{ color: 'var(--muted-foreground)' }}>
              Ask questions in the AI Playground or adjust your search/language filter to inspect cached entries.
            </p>
          </div>
        ) : (
          <div className="custom-scrollbar max-h-[calc(100vh-370px)] min-h-[260px] overflow-y-auto overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead
                className="sticky top-0 z-10 text-xs font-medium border-b"
                style={{
                  backgroundColor: 'var(--muted)',
                  color: 'var(--muted-foreground)',
                  borderColor: 'var(--border)',
                }}
              >
                <tr>
                  <th className="px-4 py-3">Cached Query</th>
                  <th className="px-3 py-3">Model</th>
                  <th className="px-3 py-3">Language</th>
                  <th className="px-3 py-3">Hits</th>
                  <th className="px-3 py-3">Tokens Saved</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: 'var(--border)' }}>
                {filteredItems.map((entry) => {
                  const totalSaved = entry.hit_count * (entry.input_tokens + entry.output_tokens);
                  const tokensPerHit = entry.input_tokens + entry.output_tokens;
                  return (
                    <tr
                      key={entry.id}
                      onClick={() => setSelectedEntry(entry)}
                      className="cursor-pointer transition-colors hover:bg-[var(--muted)]/45"
                    >
                      <td className="px-4 py-3 max-w-md relative group">
                        <div
                          className="font-medium truncate"
                          style={{ color: 'var(--foreground)' }}
                        >
                          {entry.query}
                        </div>
                        <div
                          className="pointer-events-none hidden group-hover:block absolute left-4 top-full z-30 mt-1 w-96 rounded-xl border p-3 text-xs shadow-lg whitespace-normal break-words"
                          style={{
                            backgroundColor: 'var(--card)',
                            borderColor: 'var(--border)',
                            color: 'var(--foreground)',
                          }}
                        >
                          {entry.query}
                        </div>
                        <div
                          className="text-[11px] truncate mt-0.5"
                          style={{ color: 'var(--muted-foreground)' }}
                        >
                          {entry.response.slice(0, 90)}
                          {entry.response.length > 90 ? '…' : ''}
                        </div>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span
                          className="inline-flex items-center px-2 py-0.5 rounded-md font-mono text-[11px] border"
                          style={{
                            backgroundColor: 'var(--background)',
                            borderColor: 'var(--border)',
                            color: 'var(--foreground)',
                          }}
                        >
                          {entry.model}
                        </span>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span
                          className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium border"
                          style={{
                            backgroundColor: 'var(--accent-soft)',
                            color: 'var(--accent)',
                            borderColor: 'var(--border)',
                          }}
                        >
                          {getLanguageLabel(entry.detected_language)}
                        </span>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        {entry.hit_count > 0 ? (
                          <span
                            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium tabular-nums"
                            style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}
                          >
                            <Zap className="w-3 h-3" />
                            {entry.hit_count}
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium tabular-nums border"
                            style={{
                              backgroundColor: 'var(--muted)',
                              color: 'var(--muted-foreground)',
                              borderColor: 'var(--border)',
                            }}
                          >
                            0 · Stored
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3 tabular-nums whitespace-nowrap">
                        {entry.hit_count > 0 ? (
                          <span className="font-semibold" style={{ color: 'var(--hit-text)' }}>
                            +{totalSaved.toLocaleString()}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--muted-foreground)' }}>
                            0 ({tokensPerHit.toLocaleString()}/hit)
                          </span>
                        )}
                      </td>
                      <td
                        className="px-4 py-3 text-right whitespace-nowrap"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="inline-flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => setSelectedEntry(entry)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium rounded-md border hover:bg-[var(--muted)] transition cursor-pointer"
                            style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
                          >
                            <Eye className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
                            Inspect
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmDelete(entry)}
                            disabled={isDeleting}
                            className="p-1.5 rounded-md text-[var(--muted-foreground)] hover:text-rose-600 hover:bg-rose-500/10 transition cursor-pointer"
                            aria-label="Delete entry"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total_pages > 1 && (
          <div
            className="flex items-center justify-between px-4 py-2.5 border-t text-xs"
            style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
          >
            <span>
              Showing {(data.page - 1) * data.page_size + 1}–
              {Math.min(data.page * data.page_size, data.total)} of {data.total}
            </span>
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={data.page <= 1}
                className="px-2.5 py-1 border rounded-md hover:bg-[var(--muted)] disabled:opacity-50 transition cursor-pointer"
                style={{
                  backgroundColor: 'var(--card)',
                  borderColor: 'var(--border)',
                  color: 'var(--foreground)',
                }}
              >
                Previous
              </button>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
                disabled={data.page >= data.total_pages}
                className="px-2.5 py-1 border rounded-md hover:bg-[var(--muted)] disabled:opacity-50 transition cursor-pointer"
                style={{
                  backgroundColor: 'var(--card)',
                  borderColor: 'var(--border)',
                  color: 'var(--foreground)',
                }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Entry Detail Modal */}
      <Dialog open={Boolean(selectedEntry)} onClose={() => setSelectedEntry(null)} className="relative z-50">
        <div className="fixed inset-0 flex items-center justify-center p-4 bg-black/45 backdrop-blur-xs">
          {selectedEntry && (
            <DialogPanel
              className="border rounded-2xl shadow-2xl max-w-2xl w-full p-4 sm:p-6 space-y-4 max-h-[85vh] overflow-y-auto custom-scrollbar"
              style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <span
                    className="text-xs font-medium"
                    style={{ color: 'var(--accent)' }}
                  >
                    Cache Entry Detail
                  </span>
                  <h3 className="text-base font-medium mt-0.5" style={{ color: 'var(--foreground)' }}>
                    {selectedEntry.query}
                  </h3>
                  <p
                    className="text-[11px] font-mono mt-1 break-all"
                    style={{ color: 'var(--muted-foreground)' }}
                  >
                    Normalized: {selectedEntry.normalized_query}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedEntry(null)}
                  className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition cursor-pointer"
                  style={{ color: 'var(--muted-foreground)' }}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div
                className="grid grid-cols-2 sm:grid-cols-4 gap-3 py-3 border-y text-xs"
                style={{ borderColor: 'var(--border)' }}
              >
                <div>
                  <span className="block text-[11px]" style={{ color: 'var(--muted-foreground)' }}>
                    Language
                  </span>
                  <span className="font-semibold" style={{ color: 'var(--foreground)' }}>
                    {getLanguageLabel(selectedEntry.detected_language)}
                  </span>
                </div>
                <div>
                  <span className="block text-[11px]" style={{ color: 'var(--muted-foreground)' }}>
                    Model
                  </span>
                  <span
                    className="font-mono font-semibold truncate block"
                    style={{ color: 'var(--foreground)' }}
                    title={selectedEntry.model}
                  >
                    {selectedEntry.model}
                  </span>
                </div>
                <div>
                  <span className="block text-[11px]" style={{ color: 'var(--muted-foreground)' }}>
                    Hit Count
                  </span>
                  <span
                    className="font-semibold tabular-nums"
                    style={{ color: 'var(--stat-number, var(--foreground))' }}
                  >
                    {selectedEntry.hit_count} hits
                  </span>
                </div>
                <div>
                  <span className="block text-[11px]" style={{ color: 'var(--muted-foreground)' }}>
                    Tokens (In / Out)
                  </span>
                  <span
                    className="font-semibold tabular-nums"
                    style={{ color: 'var(--foreground)' }}
                  >
                    {selectedEntry.input_tokens} / {selectedEntry.output_tokens}
                  </span>
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label
                    className="text-xs font-medium"
                    style={{ color: 'var(--muted-foreground)' }}
                  >
                    Cached LLM Response
                  </label>
                  <button
                    type="button"
                    onClick={() => handleCopyResponse(selectedEntry)}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-md border text-[11px] font-medium hover:bg-[var(--muted)] transition cursor-pointer"
                    style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
                  >
                    {copiedId === selectedEntry.id ? (
                      <>
                        <Check className="w-3 h-3" style={{ color: 'var(--hit-text)' }} />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3" />
                        Copy
                      </>
                    )}
                  </button>
                </div>
                <div
                  className="custom-scrollbar p-4 border rounded-xl text-xs sm:text-sm whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto"
                  style={{
                    backgroundColor: 'var(--code-bg)',
                    color: 'var(--code-text)',
                    borderColor: 'var(--border)',
                  }}
                >
                  {selectedEntry.response}
                </div>
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  type="button"
                  onClick={() => setConfirmDelete(selectedEntry)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border text-rose-600 hover:bg-rose-500/10 transition cursor-pointer"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Invalidate Entry
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedEntry(null)}
                  className="px-4 py-1.5 text-xs font-semibold rounded-lg hover:opacity-90 transition cursor-pointer"
                  style={{
                    backgroundColor: 'var(--accent)',
                    color: 'var(--accent-foreground)',
                  }}
                >
                  Close
                </button>
              </div>
            </DialogPanel>
          )}
        </div>
      </Dialog>

      {/* Delete Confirmation Modal */}
      <Dialog open={Boolean(confirmDelete)} onClose={() => setConfirmDelete(null)} className="relative z-50">
        <div className="fixed inset-0 flex items-center justify-center p-4 bg-black/45 backdrop-blur-xs">
          {confirmDelete && (
            <DialogPanel
              className="border rounded-2xl shadow-2xl max-w-md w-full p-5 space-y-4"
              style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
            >
              <div>
                <h3 className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>
                  Invalidate Cache Entry?
                </h3>
                <p className="text-xs mt-1" style={{ color: 'var(--muted-foreground)' }}>
                  Future similar prompts will execute a fresh LLM call until re-cached.
                </p>
                <div
                  className="mt-3 p-2.5 rounded-lg border text-xs font-medium truncate"
                  style={{
                    backgroundColor: 'var(--background)',
                    borderColor: 'var(--border)',
                    color: 'var(--foreground)',
                  }}
                >
                  {confirmDelete.query}
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmDelete(null)}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg border hover:bg-[var(--muted)] transition cursor-pointer"
                  style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDelete}
                  disabled={isDeleting}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-60 transition cursor-pointer"
                >
                  {isDeleting ? 'Deleting...' : 'Delete Entry'}
                </button>
              </div>
            </DialogPanel>
          )}
        </div>
      </Dialog>
    </div>
  );
}
