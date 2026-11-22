import { EventStreamContentType, fetchEventSource } from '@microsoft/fetch-event-source';

export type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  provider?: string | null;
  model_id?: string | null;
  created_at?: string;
  status_text?: string;
  switched_note?: string;
  is_error?: boolean;
  cache_telemetry?: {
    hit: boolean;
    cache_type: string;
    cache_source?: string;
    effective_response_language?: string;
    similarity_score?: number;
    lookup_latency_ms: number;
    saved_tokens?: number;
  };
};

export type Conversation = {
  id: string;
  title: string;
  selected_provider: string;
  selected_model: string;
  updated_at: string;
  messages?: Message[];
};

export type ServerEvent = { event: string; data: Record<string, unknown> };
export type TTSResponse = { audio_base64: string; audio_mime_type: string };

export const API = '/api/v1';

async function readError(response: Response) {
  try {
    const body = await response.json();
    return typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}).`;
  } catch {
    return `Request failed (${response.status}).`;
  }
}

export async function consumeChatStream(
  payload: { conversation_id: string | null; message: string; provider: string; model: string },
  signal: AbortSignal,
  onEvent: (event: ServerEvent) => void,
) {
  await fetchEventSource(`${API}/chat/completions`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
    signal,
    openWhenHidden: true,
    async onopen(response) {
      const contentType = response.headers.get('content-type') || '';
      if (response.ok && contentType.includes(EventStreamContentType)) return;
      if (!response.ok) throw new Error(await readError(response));
      throw new Error(`Unexpected response content-type: ${contentType || 'unknown'}`);
    },
    onmessage(msg) {
      if (!msg.data) return;
      const eventName = msg.event || 'message';
      try {
        onEvent({ event: eventName, data: JSON.parse(msg.data) as Record<string, unknown> });
      } catch {
        onEvent({ event: eventName, data: { text: msg.data } });
      }
    },
    onerror(err) {
      // Rethrow immediately so fetchEventSource never auto-retries failed LLM POST completions.
      throw err;
    },
  });
}
