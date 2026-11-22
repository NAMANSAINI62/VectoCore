import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

export interface CacheEntry {
  id: string;
  query: string;
  normalized_query: string;
  response: string;
  detected_language: string;
  intent: string;
  depth_scope: string;
  critical_entities: string[];
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  hit_count: number;
  status: string;
  created_at: string;
  expires_at: string;
  last_hit_at: string | null;
}

export interface CacheEntriesResponse {
  items: CacheEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface RelatedCacheMatchItem {
  entry_id: string;
  query: string;
  similarity_score: number;
  detected_language: string;
  model: string;
  hit_count: number;
}

export interface SemanticMatchCandidateItem {
  rank?: number | null;
  cache_entry_id?: string | null;
  previous_query: string;
  similarity_score: number;
  intent_compatible: boolean;
  intent_status: string;
  confidence: number;
  intent_summary: string;
  reason: string;
  detected_language: string;
  model: string;
  selected: boolean;
}

export interface SemanticMatchInsights {
  current_query: string;
  cache_decision: 'HIT' | 'MISS' | string;
  cache_status: string;
  similarity_threshold?: number;
  stage2_recall_floor?: number;
  matched_queries: SemanticMatchCandidateItem[];
  selected_cache_entry_id?: string | null;
  selected_previous_query?: string | null;
  returned_cached_response?: string | null;
  validation_explanation?: string | null;
  rejected_candidates: SemanticMatchCandidateItem[];
}

export interface TelemetryItem {
  id: string;
  request_id?: string;
  query_preview: string;
  cache_status: 'exact_hit' | 'semantic_hit' | 'miss' | 'bypass' | 'error' | string;
  provider: string;
  model: string;
  detected_language: string;
  input_tokens: number;
  output_tokens: number;
  tokens_saved: number;
  cache_lookup_latency_ms: number;
  llm_latency_ms?: number;
  total_latency_ms: number;
  similarity_score: number | null;
  matched_entry_id?: string | null;
  matched_query?: string | null;
  response_preview?: string | null;
  related_candidates?: RelatedCacheMatchItem[] | null;
  error_type?: string | null;
  error_message?: string | null;
  semantic_match_insights?: SemanticMatchInsights | null;
  created_at: string;
}

export interface CacheStatsResponse {
  total_requests: number;
  cache_hits: number;
  cache_misses: number;
  hit_rate_pct: number;
  exact_hits: number;
  semantic_hits: number;
  exact_hit_rate_pct?: number;
  semantic_hit_rate_pct?: number;
  llm_calls_avoided?: number;
  real_tokens_saved: number;
  input_tokens_saved?: number;
  output_tokens_saved?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  avg_hit_latency_ms: number;
  avg_exact_hit_latency_ms?: number;
  avg_semantic_hit_latency_ms?: number;
  avg_miss_latency_ms: number;
  avg_overall_latency_ms?: number;
  p50_latency_ms?: number;
  p95_latency_ms?: number;
  p99_latency_ms?: number;
  p50_hit_latency_ms?: number;
  p95_hit_latency_ms?: number;
  p99_hit_latency_ms?: number;
  p50_miss_latency_ms?: number;
  p95_miss_latency_ms?: number;
  p99_miss_latency_ms?: number;
  total_entries_count: number;
  recent_activity: TelemetryItem[];
  daily_trends?: DailyTrendPoint[];
  model_usage?: ModelUsageStat[];
  latency_buckets?: LatencyBucketStat[];
  embedding_model_info?: EmbeddingModelInfo | null;
}

export interface DailyTrendPoint {
  date: string;
  hits: number;
  misses: number;
  exact_hits?: number;
  semantic_hits?: number;
  requests: number;
  hit_rate_pct?: number;
  tokens_saved: number;
  input_tokens_saved?: number;
  output_tokens_saved?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  avg_latency_ms: number;
}

export interface LatencyBucketStat {
  bucket: string;
  exact_hits: number;
  semantic_hits: number;
  misses: number;
  count: number;
}

export interface ModelUsageStat {
  provider: string;
  model: string;
  requests: number;
  hits: number;
  misses: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  tokens_saved: number;
  avg_latency_ms: number;
}

export interface EmbeddingModelInfo {
  name: string;
  dimensions: number;
  status: string;
}

export interface ConfiguredModel {
  id: string;
  name: string;
  provider: string;
}

export interface ConfiguredProvider {
  id: string;
  configured: boolean;
  models: string[];
}

export interface CacheStatsParams {
  days?: number;
  start_date?: string;
  end_date?: string;
  activity_limit?: number;
}

export interface CacheSettings {
  similarity_threshold: number;
  default_ttl_hours: number;
}

export const cacheApi = createApi({
  reducerPath: 'cacheApi',
  baseQuery: fetchBaseQuery({
    baseUrl: '/api/v1',
    credentials: 'include',
  }),
  keepUnusedDataFor: 300,
  tagTypes: ['CacheEntries', 'CacheStats', 'CacheSettings'],
  endpoints: (builder) => ({
    getCacheEntries: builder.query<
      CacheEntriesResponse,
      { page?: number; pageSize?: number; search?: string; language?: string; intent?: string }
    >({
      query: (params) => {
        const queryParams = new URLSearchParams();
        if (params.page) queryParams.set('page', params.page.toString());
        if (params.pageSize) queryParams.set('page_size', params.pageSize.toString());
        if (params.search) queryParams.set('search', params.search);
        if (params.language) queryParams.set('language', params.language);
        if (params.intent) queryParams.set('intent', params.intent);
        return `cache/entries?${queryParams.toString()}`;
      },
      providesTags: ['CacheEntries'],
    }),

    getCacheStats: builder.query<CacheStatsResponse, CacheStatsParams | void>({
      query: (params) => {
        if (!params) return 'cache/stats';
        const queryParams = new URLSearchParams();
        if (params.days) queryParams.set('days', params.days.toString());
        if (params.start_date) queryParams.set('start_date', params.start_date);
        if (params.end_date) queryParams.set('end_date', params.end_date);
        if (params.activity_limit !== undefined) {
          queryParams.set('activity_limit', params.activity_limit.toString());
        }
        const qs = queryParams.toString();
        return qs ? `cache/stats?${qs}` : 'cache/stats';
      },
      providesTags: ['CacheStats'],
    }),

    inspectTelemetryItem: builder.query<TelemetryItem, string>({
      query: (telemetryId) => `cache/telemetry/${telemetryId}/inspect`,
    }),

    getModels: builder.query<ConfiguredModel[], void>({
      query: () => 'models',
    }),

    getProviders: builder.query<ConfiguredProvider[], void>({
      query: () => 'providers',
    }),

    getCacheSettings: builder.query<CacheSettings, void>({
      query: () => 'cache/settings',
      providesTags: ['CacheSettings'],
    }),

    updateCacheSettings: builder.mutation<CacheSettings, Partial<CacheSettings>>({
      query: (body) => ({
        url: 'cache/settings',
        method: 'PATCH',
        body,
      }),
      invalidatesTags: ['CacheSettings'],
    }),

    deleteCacheEntry: builder.mutation<void, string>({
      query: (entryId) => ({
        url: `cache/entries/${entryId}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['CacheEntries', 'CacheStats'],
    }),
  }),
});

export const {
  useGetCacheEntriesQuery,
  useGetCacheStatsQuery,
  useInspectTelemetryItemQuery,
  useLazyInspectTelemetryItemQuery,
  useGetModelsQuery,
  useGetProvidersQuery,
  useGetCacheSettingsQuery,
  useUpdateCacheSettingsMutation,
  useDeleteCacheEntryMutation,
} = cacheApi;
