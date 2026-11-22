'use client';

import React from 'react';
import { Dialog, DialogPanel } from '@headlessui/react';
import { TelemetryItem } from '@/store/cacheApi';
import { X, Zap, Sparkles } from 'lucide-react';
import { getLanguageLabel } from '@/lib/languages';

export function getBadgeLabel(status: string): string {
  const labels: Record<string, string> = {
    exact_hit: 'EXACT HIT',
    semantic_hit: 'SEMANTIC HIT',
    blocked: 'BLOCKED',
    error: 'ERROR',
    bypass: 'BYPASS',
  };
  return labels[status] ?? 'MISS';
}

export function getBadgeStyle(status: string): React.CSSProperties {
  if (status === 'exact_hit' || status === 'semantic_hit') {
    return { backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' };
  }
  if (status === 'blocked') {
    return { backgroundColor: 'rgba(245, 158, 11, 0.14)', color: '#d97706' };
  }
  if (status === 'error') {
    return { backgroundColor: 'rgba(239, 68, 68, 0.14)', color: '#dc2626' };
  }
  if (status === 'bypass') {
    return { backgroundColor: 'var(--muted)', color: 'var(--muted-foreground)' };
  }
  return { backgroundColor: 'var(--miss-bg)', color: 'var(--miss-text)' };
}

function CodeBox({ children, maxH = 'max-h-44' }: { children: React.ReactNode; maxH?: string }) {
  return (
    <div
      className={`custom-scrollbar p-3 rounded-lg border border-[var(--border)] text-xs leading-relaxed ${maxH} overflow-y-auto whitespace-pre-wrap`}
      style={{ backgroundColor: 'var(--code-bg)', color: 'var(--code-text)' }}
    >
      {children}
    </div>
  );
}

export function TelemetryTraceModal({
  activeLog,
  inspecting,
  onClose,
}: {
  activeLog: TelemetryItem | null;
  inspecting: boolean;
  onClose: () => void;
}) {
  const insights = activeLog?.semantic_match_insights ?? null;
  const isHit = activeLog?.cache_status === 'exact_hit' || activeLog?.cache_status === 'semantic_hit';

  const renderSemanticInsights = () => {
    if (!activeLog || !insights) return null;
    const isSemanticHit = activeLog.cache_status === 'semantic_hit';
    const isMiss = activeLog.cache_status === 'miss';
    if (!isSemanticHit && !isMiss) return null;

    if (isMiss) {
      const friendlyReason =
        'No matching cached answer was found for this question, so a fresh response was generated directly by the AI model.';
      return (
        <div className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--secondary)]/25 p-4">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--foreground)]">Reason</p>
            <p className="text-xs text-[var(--muted-foreground)] leading-relaxed">{friendlyReason}</p>
          </div>
          {insights.rejected_candidates.length > 0 && (
            <details className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-2.5">
              <summary className="cursor-pointer text-[11px] font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] select-none">
                Rejected Semantic Candidates ({insights.rejected_candidates.length})
              </summary>
              <div className="mt-2.5 space-y-2">
                {insights.rejected_candidates.map((rej, idx) => (
                  <div key={`${rej.cache_entry_id || idx}-rej-${idx}`} className="p-2.5 rounded-lg border border-[var(--border)] bg-[var(--secondary)]/30 space-y-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ backgroundColor: 'var(--miss-bg)', color: 'var(--miss-text)' }}>
                        {rej.intent_status || 'Incompatible'}
                      </span>
                      <span className="text-[11px] font-mono text-[var(--muted-foreground)]">
                        Similarity: {rej.similarity_score.toFixed(4)} ({(rej.similarity_score * 100).toFixed(1)}%)
                      </span>
                    </div>
                    <p className="text-xs text-[var(--foreground)] whitespace-pre-wrap">{rej.previous_query}</p>
                    {rej.reason && <p className="text-[11px] text-[var(--muted-foreground)]">{rej.reason}</p>}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      );
    }

    const matched = insights.matched_queries[0];
    const threshold = insights.similarity_threshold ?? 0.82;
    const recallFloor = insights.stage2_recall_floor ?? 0.58;
    const simScore = matched?.similarity_score ?? activeLog.similarity_score ?? null;
    const decisionLabel = 'SEMANTIC HIT';
    const matchedQueryText = matched?.previous_query || insights.selected_previous_query || activeLog.matched_query || null;

    const base = insights.validation_explanation?.trim();
    const whyText =
      simScore !== null
        ? simScore >= threshold
          ? base || `Cosine similarity (${simScore.toFixed(4)}) met the configured threshold (${threshold.toFixed(4)}) and passed intent compatibility validation.`
          : `Similarity (${simScore.toFixed(4)}) fell inside the two-stage recall window (${recallFloor.toFixed(4)}–${threshold.toFixed(4)}) and Stage-2 intent validation confirmed equivalence${base ? `: ${base}` : '.'}`
        : base || 'Matched previously cached query.';

    return (
      <div className="space-y-3 rounded-xl border border-[var(--border)] bg-[var(--secondary)]/25 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--foreground)]">Semantic Match Insights</p>
            <p className="text-[11px] text-[var(--muted-foreground)] mt-0.5">Two-stage vector retrieval + intent compatibility validation</p>
          </div>
          <span
            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold"
            style={insights.cache_decision === 'HIT' ? { backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' } : { backgroundColor: 'var(--miss-bg)', color: 'var(--miss-text)' }}
          >
            {decisionLabel}
          </span>
        </div>

        {isSemanticHit && (
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
              Matched Cached Query ({matchedQueryText ? '1/1' : '0/1'})
            </p>
            {matchedQueryText ? (
              <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--card)] space-y-1.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-[var(--secondary)] text-[var(--foreground)]">#{matched?.rank ?? 1}</span>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}>Selected Match</span>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}>{matched?.intent_status || 'Compatible'}</span>
                  </div>
                  {simScore !== null && (
                    <div className="text-[11px] font-mono text-[var(--foreground)]">
                      Similarity: <strong>{simScore.toFixed(4)}</strong> ({(simScore * 100).toFixed(1)}%)
                    </div>
                  )}
                </div>
                <p className="text-xs text-[var(--foreground)] font-medium whitespace-pre-wrap">{matchedQueryText}</p>
              </div>
            ) : (
              <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--card)] text-xs text-[var(--muted-foreground)]">
                No intent-compatible cached queries matched.
              </div>
            )}
          </div>
        )}

        <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--card)] space-y-2 text-xs">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--foreground)]">Validation Summary</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
            <div className="rounded-md bg-[var(--secondary)]/40 px-2.5 py-1.5">
              <span className="text-[var(--muted-foreground)] block">Decision</span>
              <span className="font-semibold text-[var(--foreground)]">{decisionLabel}</span>
            </div>
            <div className="rounded-md bg-[var(--secondary)]/40 px-2.5 py-1.5">
              <span className="text-[var(--muted-foreground)] block">Similarity Score</span>
              <span className="font-mono font-semibold text-[var(--foreground)]">
                {simScore !== null ? `${simScore.toFixed(4)} (${(simScore * 100).toFixed(1)}%)` : 'N/A'}
              </span>
            </div>
            <div className="rounded-md bg-[var(--secondary)]/40 px-2.5 py-1.5">
              <span className="text-[var(--muted-foreground)] block">Configured Threshold</span>
              <span className="font-mono font-semibold text-[var(--foreground)]">
                {threshold.toFixed(4)} ({(threshold * 100).toFixed(1)}%)
              </span>
            </div>
          </div>
          <p className="text-[11px] text-[var(--muted-foreground)] leading-relaxed">
            <strong className="text-[var(--foreground)]">Why:</strong> {whyText}
          </p>
        </div>

        {insights.rejected_candidates.length > 0 && (
          <details className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-2.5">
            <summary className="cursor-pointer text-[11px] font-semibold text-[var(--muted-foreground)] hover:text-[var(--foreground)] select-none">
              Rejected Semantic Candidates ({insights.rejected_candidates.length})
            </summary>
            <div className="mt-2.5 space-y-2">
              {insights.rejected_candidates.map((rej, idx) => (
                <div key={`${rej.cache_entry_id || idx}-rej-${idx}`} className="p-2.5 rounded-lg border border-[var(--border)] bg-[var(--secondary)]/30 space-y-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ backgroundColor: 'var(--miss-bg)', color: 'var(--miss-text)' }}>
                      {rej.intent_status || 'Incompatible'}
                    </span>
                    <span className="text-[11px] font-mono text-[var(--muted-foreground)]">
                      Similarity: {rej.similarity_score.toFixed(4)} ({(rej.similarity_score * 100).toFixed(1)}%)
                    </span>
                  </div>
                  <p className="text-xs text-[var(--foreground)] whitespace-pre-wrap">{rej.previous_query}</p>
                  {rej.reason && <p className="text-[11px] text-[var(--muted-foreground)]">{rej.reason}</p>}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    );
  };

  return (
    <Dialog open={Boolean(activeLog)} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 flex items-center justify-center p-4 bg-black/45 backdrop-blur-xs">
        {activeLog && (
          <DialogPanel className="bg-[var(--card)] border border-[var(--border)] rounded-2xl shadow-2xl max-w-2xl w-full p-5 sm:p-6 space-y-4 max-h-[88vh] overflow-y-auto custom-scrollbar animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="text-[11px] uppercase tracking-wider font-bold text-[var(--accent)]">Request Execution Trace</span>
                <p className="font-mono text-xs text-[var(--muted-foreground)] mt-0.5">
                  {activeLog.request_id || `req-${activeLog.id.slice(0, 8)}`}
                </p>
              </div>
              <button type="button" aria-label="Close modal" onClick={onClose} className="p-1.5 rounded-lg hover:bg-[var(--muted)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex flex-wrap items-start justify-between gap-4 py-3 border-y border-[var(--border)] text-xs">
              <div>
                <span className="text-[var(--muted-foreground)] block">Cache Outcome</span>
                <span className="inline-flex items-center mt-1 px-2 py-0.5 rounded-full font-semibold text-[10px] uppercase" style={getBadgeStyle(activeLog.cache_status)}>
                  {getBadgeLabel(activeLog.cache_status)}
                </span>
              </div>
              {isHit && (
                <div>
                  <span className="text-[var(--muted-foreground)] block">Cache Lookup</span>
                  <span className="font-mono font-semibold text-[var(--foreground)] mt-1 block">{activeLog.cache_lookup_latency_ms}ms</span>
                </div>
              )}
              {!isHit && (
                <div>
                  <span className="text-[var(--muted-foreground)] block">LLM Latency</span>
                  <span className="font-mono font-semibold text-[var(--foreground)] mt-1 block">
                    {activeLog.llm_latency_ms ?? Math.max(0, activeLog.total_latency_ms - activeLog.cache_lookup_latency_ms)}ms
                  </span>
                </div>
              )}
              {activeLog.cache_status !== 'miss' && (
                <div>
                  <span className="text-[var(--muted-foreground)] block">Total Latency</span>
                  <span className="font-mono font-semibold mt-1 block" style={{ color: 'var(--stat-number)' }}>{activeLog.total_latency_ms}ms</span>
                </div>
              )}
              <div>
                <span className="text-[var(--muted-foreground)] block">Language</span>
                <span className="font-semibold text-[var(--foreground)] mt-1 block">{getLanguageLabel(activeLog.detected_language)}</span>
              </div>
            </div>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">User&apos;s Current Query</p>
                <CodeBox maxH="max-h-28">{insights?.current_query || activeLog.query_preview}</CodeBox>
              </div>

              {isHit && (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--background)]/60 p-3.5 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold" style={{ backgroundColor: 'var(--hit-bg)', color: 'var(--hit-text)' }}>
                      {activeLog.cache_status === 'exact_hit' ? <Zap className="w-3.5 h-3.5" /> : <Sparkles className="w-3.5 h-3.5" />}
                      {activeLog.cache_status === 'exact_hit' ? 'Exact Cache Match' : 'PostgreSQL Semantic Match'} · +{activeLog.tokens_saved} tokens saved
                    </span>
                    {activeLog.cache_status === 'exact_hit' ? (
                      <span className="font-mono text-[11px] text-[var(--muted-foreground)]">100% SHA-256 Key Match</span>
                    ) : activeLog.similarity_score !== null && activeLog.similarity_score !== undefined ? (
                      <span className="font-mono text-xs font-bold" style={{ color: 'var(--stat-number)' }}>
                        {(activeLog.similarity_score * 100).toFixed(1)}% Similarity Score
                      </span>
                    ) : null}
                  </div>

                  {(activeLog.cache_status === 'exact_hit' ? activeLog.matched_query : !insights) && (
                    <div className="space-y-1">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] block">
                        {activeLog.cache_status === 'exact_hit' ? 'Original Exact Cached Query' : 'Matched Original Cached Query'}
                      </span>
                      <p className="text-xs font-medium text-[var(--foreground)] bg-[var(--card)] px-3 py-2 rounded-lg border border-[var(--border)]">
                        {inspecting && !activeLog.matched_query ? 'Loading matched query...' : activeLog.matched_query || activeLog.query_preview}
                      </p>
                    </div>
                  )}

                  <div className="space-y-1">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] block">
                      {activeLog.cache_status === 'exact_hit' ? 'Exact Cached LLM Response Returned' : 'Cached LLM Response Returned to User'}
                    </span>
                    <CodeBox>
                      {inspecting && !insights?.returned_cached_response && !activeLog.response_preview
                        ? 'Loading cached response...'
                        : insights?.returned_cached_response || activeLog.response_preview || 'Cached response served.'}
                    </CodeBox>
                  </div>
                </div>
              )}

              {activeLog.cache_status === 'miss' && activeLog.response_preview && (
                <div className="space-y-1">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] block">
                    Newly Generated LLM Response (Fresh API Execution)
                  </span>
                  <CodeBox maxH="max-h-36">{activeLog.response_preview}</CodeBox>
                </div>
              )}

              {(activeLog.cache_status === 'error' || activeLog.cache_status === 'bypass') && (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--background)]/60 p-3.5 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase" style={getBadgeStyle(activeLog.cache_status)}>
                      {getBadgeLabel(activeLog.cache_status)}
                    </span>
                    {activeLog.error_type && <span className="font-mono text-[11px] text-[var(--muted-foreground)]">{activeLog.error_type}</span>}
                  </div>
                  <p className="text-xs text-[var(--muted-foreground)]">
                    {activeLog.error_message || activeLog.response_preview || (activeLog.cache_status === 'bypass' ? 'Context-dependent follow-up bypassed global semantic cache.' : 'Execution failed before a response could be cached.')}
                  </p>
                </div>
              )}
            </div>

            {renderSemanticInsights()}

            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--muted-foreground)] pt-1">
              <span>
                Input: <strong className="text-[var(--foreground)]">{activeLog.input_tokens}</strong> · Output: <strong className="text-[var(--foreground)]">{activeLog.output_tokens}</strong>
              </span>
              <button type="button" onClick={onClose} className="px-4 py-1.5 text-xs font-semibold bg-[var(--accent)] text-[var(--accent-foreground)] rounded-lg hover:opacity-90 transition cursor-pointer">
                Close
              </button>
            </div>
          </DialogPanel>
        )}
      </div>
    </Dialog>
  );
}
