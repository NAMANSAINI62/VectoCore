export const CHART_COLORS = {
  exactHit: 'var(--chart-exact)',
  semanticHit: 'var(--chart-semantic)',
  miss: 'var(--chart-miss)',
  input: 'var(--chart-input)',
  output: 'var(--chart-output)',
  savings: 'var(--chart-savings)',
  neutral: 'var(--chart-neutral)',
  accent: 'var(--accent)',
  grid: 'var(--chart-grid)',
  axis: 'var(--chart-axis)',
  stat: 'var(--stat-number)',
} as const;

export const AXIS_TICK_STYLE = {
  fontSize: 11,
  fill: 'var(--chart-axis)',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
} as const;

export const GRID_PROPS = {
  strokeDasharray: '3 3',
  stroke: 'var(--chart-grid)',
  vertical: false,
} as const;

const CHART_ANIMATION_PROPS = {
  isAnimationActive: true,
  animationDuration: 950,
  animationEasing: 'cubic-bezier(0.22,1,0.36,1)',
} as const;

export function getChartAnimationProps(animationBegin = 0) {
  return {
    ...CHART_ANIMATION_PROPS,
    animationBegin,
  };
}

export const ACTIVE_DOT_STYLE = {
  r: 5,
  strokeWidth: 2,
  stroke: 'var(--card)',
} as const;

export function formatCompactNumber(value: number): string {
  if (!Number.isFinite(value)) return '0';
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString();
}

export function formatShortDate(dateStr: string): string {
  if (!dateStr) return dateStr;
  if (dateStr.length >= 16 && dateStr[10] === ' ') {
    return dateStr.slice(5, 16);
  }
  if (dateStr.length < 10) return dateStr;
  return dateStr.slice(5);
}

const KNOWN_MODEL_DISPLAY_NAMES: Record<string, string> = {
  'openai/gpt-oss-20b': 'GPT-OSS 20B',
  'openai/gpt-oss-120b': 'GPT-OSS 120B',
  'command-a-03-2025': 'Command A',
  'nvidia/nemotron-3.5-bolt-e4b': 'Nemotron 3.5 Bolt',
  'nvidia/nemotron-3.5-super-vl-120b-a12b': 'Nemotron 3.5 Super VL',
  'gemini-3-flash-preview': '3 Flash',
  'gemini-flash-lite-latest': 'Flash-Lite',
  'gemini-3.5-flash-lite': '3.5 Flash-Lite',
  'gemini-3.1-flash-lite': '3.1 Flash-Lite',
  'gemini-3.1-flash-lite-preview': '3.1 Lite Prev',
  'baidu/ernie-5.5-flash-preview:free': 'ERNIE 5.5 Flash',
};

export function formatModelShortName(model: string): string {
  const clean = (model || '').trim();
  if (KNOWN_MODEL_DISPLAY_NAMES[clean]) {
    return KNOWN_MODEL_DISPLAY_NAMES[clean];
  }
  const tail = (clean.split('/').pop() ?? clean).replace(/:free$/i, '').replace(/-preview$/i, '');
  return tail.length > 20 ? `${tail.slice(0, 18)}…` : tail;
}

export function formatLatencyMs(ms: number): string {
  if (!Number.isFinite(ms)) return '0ms';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}
