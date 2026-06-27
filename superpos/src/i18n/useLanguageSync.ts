import { useEffect } from 'react';
import { AxiosError } from 'axios';
import apiClient from '../api/client';
import { useAuthStore } from '../store/authStore';
import {
  SUPPORTED_LANGUAGES,
  type SupportedLanguage,
  applyTenantOverrides,
  setLanguage,
} from './index';

interface TranslationsPayload {
  language: SupportedLanguage;
  overrides: Record<string, unknown>;
  count: number;
}

/**
 * Wire the active i18next language + tenant overrides to the auth store.
 *
 * - On mount / when `tenant_language` changes: switch i18next + flip <html dir>.
 * - On mount / when `tenant`/`language` changes: fetch tenant overrides for
 *   the active language and merge them on top of the bundled base.
 *
 * Mount this once near the root (App.tsx).
 */
export function useLanguageSync(): void {
  const language = useAuthStore((s) => s.user?.tenant_language) ?? 'en';
  const tenantId = useAuthStore((s) => s.user?.tenant) ?? null;
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // 1. Switch i18next + document direction.
  useEffect(() => {
    const lang: SupportedLanguage = (SUPPORTED_LANGUAGES as readonly string[]).includes(language)
      ? (language as SupportedLanguage)
      : 'en';
    setLanguage(lang);
  }, [language]);

  // 2. Fetch overrides whenever the tenant / language changes.
  useEffect(() => {
    if (!isAuthenticated || !tenantId) return;
    const lang: SupportedLanguage = (SUPPORTED_LANGUAGES as readonly string[]).includes(language)
      ? (language as SupportedLanguage)
      : 'en';

    let cancelled = false;
    apiClient
      .get<TranslationsPayload>(`/accounts/tenant/translations/${lang}/`)
      .then((resp) => {
        if (cancelled) return;
        applyTenantOverrides(lang, resp.data.overrides ?? {});
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // 404 just means no overrides yet — apply an empty patch to re-seed
        // the base resources. Other errors are non-fatal; we keep whatever
        // resources are already in i18next.
        if (err instanceof AxiosError && err.response?.status === 404) {
          applyTenantOverrides(lang, {});
        }
      });

    return () => { cancelled = true; };
  }, [isAuthenticated, tenantId, language]);
}
