import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import enBase from './locales/en.json';
import arBase from './locales/ar.json';

export const SUPPORTED_LANGUAGES = ['en', 'ar'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export const RTL_LANGUAGES: ReadonlySet<SupportedLanguage> = new Set(['ar']);

export const isRtl = (lang: string): boolean => RTL_LANGUAGES.has(lang as SupportedLanguage);

/**
 * Bundle the base translations that ship with the app. Per-tenant overrides
 * are merged on top of these at runtime via `applyTenantOverrides`.
 */
const baseResources: Record<SupportedLanguage, { translation: Record<string, unknown> }> = {
  en: { translation: enBase as Record<string, unknown> },
  ar: { translation: arBase as Record<string, unknown> },
};

void i18n
  .use(initReactI18next)
  .init({
    resources: baseResources,
    lng: 'en',
    fallbackLng: 'en',
    supportedLngs: [...SUPPORTED_LANGUAGES],
    interpolation: { escapeValue: false },
    returnNull: false,
  });

/**
 * Apply a `<lang>` → `key → string` override dict on top of the bundled base.
 * Pass `{}` to revert. We always re-seed the base first so consecutive calls
 * never accumulate stale entries.
 */
export function applyTenantOverrides(lang: SupportedLanguage, overrides: Record<string, unknown>): void {
  i18n.addResourceBundle(lang, 'translation', baseResources[lang].translation, true, true);
  if (overrides && Object.keys(overrides).length > 0) {
    i18n.addResourceBundle(lang, 'translation', overrides, true, true);
  }
}

/** Switch the active language and flip the document direction for RTL locales. */
export function setLanguage(lang: SupportedLanguage): void {
  void i18n.changeLanguage(lang);
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang;
    document.documentElement.dir = isRtl(lang) ? 'rtl' : 'ltr';
  }
}

/** The bundled base for a language — used when generating the upload template. */
export function getBundledTranslations(lang: SupportedLanguage): Record<string, unknown> {
  return baseResources[lang].translation;
}

export default i18n;
