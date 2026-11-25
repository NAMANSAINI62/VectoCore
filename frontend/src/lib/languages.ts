export interface SupportedLanguage {
  code: string;
  label: string;
}

// These codes match the language aliases accepted by the cache entries API.
export const SUPPORTED_LANGUAGES: SupportedLanguage[] = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'hinglish', label: 'Hinglish' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
];

export const QUICK_LANGUAGE_CODES: string[] = ['en', 'hi', 'hinglish'];

const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English',
  english: 'English',
  hi: 'Hindi',
  hindi: 'Hindi',
  hinglish: 'Hinglish',
  es: 'Spanish',
  spanish: 'Spanish',
  fr: 'French',
  french: 'French',
  zh: 'Chinese',
  chinese: 'Chinese',
  ja: 'Japanese',
  japanese: 'Japanese',
  de: 'German',
  german: 'German',
  ar: 'Arabic',
  arabic: 'Arabic',
  pt: 'Portuguese',
  portuguese: 'Portuguese',
  ko: 'Korean',
  korean: 'Korean',
  ru: 'Russian',
  russian: 'Russian',
  it: 'Italian',
  italian: 'Italian',
};

export function getLanguageLabel(language: string | null | undefined): string {
  const value = language?.trim();
  if (!value) return 'Unknown';

  return LANGUAGE_LABELS[value.toLowerCase()] ?? value;
}
