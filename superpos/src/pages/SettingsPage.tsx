import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AxiosError } from 'axios';
import { differenceInDays, format, startOfDay } from 'date-fns';
import { ar, enUS } from 'date-fns/locale';
import { useTranslation } from 'react-i18next';
import apiClient from '../api/client';
import { useAuthStore } from '../store/authStore';
import { absoluteMediaUrl } from '../utils/media';
import {
  SUPPORTED_LANGUAGES,
  type SupportedLanguage,
  applyTenantOverrides,
  getBundledTranslations,
} from '../i18n';
import { Header } from '../components/layout/Header';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Icon } from '../components/ui/Icon';

/* ─────────────────────────────────────────────────────────────────────────────
 * Local primitives.
 * ──────────────────────────────────────────────────────────────────────────── */
const Field: React.FC<{ label: string; hint?: string; children: React.ReactNode; className?: string }> = ({
  label, hint, children, className = '',
}) => (
  <div className={className}>
    <label className="text-[13px] font-semibold text-neutral-700 block mb-1.5">{label}</label>
    {children}
    {hint && <div className="text-[12px] text-neutral-500 mt-1">{hint}</div>}
  </div>
);

const SettingsInput: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = ({ className = '', ...props }) => (
  <input
    {...props}
    className={`w-full h-10 px-3 rounded-md border border-neutral-300 focus-ring bg-white text-[14px] ${className}`}
  />
);

const SettingsSelect: React.FC<
  React.SelectHTMLAttributes<HTMLSelectElement> & { children: React.ReactNode }
> = ({ children, className = '', ...props }) => (
  <select
    {...props}
    className={`w-full h-10 px-3 rounded-md border border-neutral-300 focus-ring bg-white text-[14px] ${className}`}
  >
    {children}
  </select>
);

const ToggleRow: React.FC<{
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}> = ({ label, hint, checked, onChange, disabled }) => (
  <label className="flex items-center justify-between py-1.5 gap-4">
    <span className="text-[14px] flex-1">
      {label}
      {hint && <span className="block text-[12px] text-neutral-500 font-normal">{hint}</span>}
    </span>
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
      className="w-10 h-6 rounded-full appearance-none bg-neutral-300 checked:bg-brand-500 relative cursor-pointer transition
        before:absolute before:top-0.5 before:start-0.5 before:w-5 before:h-5 before:rounded-full before:bg-white
        checked:before:translate-x-4 before:transition disabled:opacity-50 disabled:cursor-not-allowed"
    />
  </label>
);

/* ─────────────────────────────────────────────────────────────────────────────
 * Settings shape — matches TenantSettingsSerializer.
 * ──────────────────────────────────────────────────────────────────────────── */
interface TenantSettings {
  id?: number;
  name: string;
  // Subscription (read-only)
  plan: 'starter' | 'growth' | 'enterprise';
  trial_ends_at: string | null;
  // Store & receipt
  phone: string;
  address: string;
  vat_number: string;
  logo: string | null;
  receipt_footer: string;
  show_tax_on_receipt: boolean;
  // Localization
  currency: string;
  language: string;
  timezone: string;
  // Hardware: printer
  printer_name: string;
  printer_connection: 'usb' | 'network' | 'bluetooth';
  printer_ip: string | null;
  // Hardware: scale
  scale_barcode_prefix: string;
  scale_connection: 'serial' | 'usb' | 'network';
  scale_export_interval: 'manual' | 'hourly' | 'daily' | 'weekly';
  // Payments
  payment_cash_enabled: boolean;
  payment_card_enabled: boolean;
  payment_wallet_enabled: boolean;
  card_terminal_type: string;
}

const EMPTY_TENANT: TenantSettings = {
  name: '',
  plan: 'starter', trial_ends_at: null,
  phone: '', address: '', vat_number: '',
  logo: null, receipt_footer: '', show_tax_on_receipt: true,
  currency: 'EGP', language: 'en', timezone: 'Africa/Cairo',
  printer_name: '', printer_connection: 'usb', printer_ip: null,
  scale_barcode_prefix: '21', scale_connection: 'serial', scale_export_interval: 'manual',
  payment_cash_enabled: true, payment_card_enabled: true,
  payment_wallet_enabled: true, card_terminal_type: '',
};

const SETTINGS_ENDPOINT = '/accounts/tenant/settings/';

type TabId =
  | 'store' | 'hardware' | 'payments' | 'localization'
  | 'translations' | 'subscription' | 'branches';

const TABS: { id: TabId; labelKey: string; icon: string; emoji: string }[] = [
  { id: 'store',        labelKey: 'settings.tabs.store',        icon: 'receipt', emoji: '🏢' },
  { id: 'hardware',     labelKey: 'settings.tabs.hardware',     icon: 'printer', emoji: '🖨️' },
  { id: 'payments',     labelKey: 'settings.tabs.payments',     icon: 'card',    emoji: '💳' },
  { id: 'localization', labelKey: 'settings.tabs.localization', icon: 'gear',    emoji: '🌍' },
  { id: 'translations', labelKey: 'settings.tabs.translations', icon: 'mail',    emoji: '🌐' },
  { id: 'subscription', labelKey: 'settings.tabs.subscription', icon: 'box',     emoji: '💎' },
  { id: 'branches',     labelKey: 'settings.tabs.branches',     icon: 'home',    emoji: '🏪' },
];

/* ─────────────────────────────────────────────────────────────────────────────
 * Settings page.
 * ──────────────────────────────────────────────────────────────────────────── */
export const SettingsPage: React.FC = () => {
  const { t } = useTranslation();
  const updateUser = useAuthStore((s) => s.updateUser);

  const [settings, setSettings]       = useState<TenantSettings>(EMPTY_TENANT);
  const [logoFile, setLogoFile]       = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [loading, setLoading]         = useState(true);
  const [saving,  setSaving]          = useState(false);
  const [toast,   setToast]           = useState<{ kind: 'success' | 'error'; msg: string } | null>(null);
  const [dirty,   setDirty]           = useState(false);
  const [activeTab, setActiveTab]     = useState<TabId>('store');

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  /* ─── Fetch existing settings on mount ────────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiClient.get<Partial<TenantSettings>>(SETTINGS_ENDPOINT)
      .then((res) => {
        if (cancelled) return;
        setSettings({ ...EMPTY_TENANT, ...res.data, logo: res.data.logo ?? null });
        setDirty(false);
      })
      .catch(() => {
        if (cancelled) return;
        setToast({ kind: 'error', msg: t('settings.loadFailed') });
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  /* ─── Build object URL for the locally selected logo preview ──────────── */
  useEffect(() => {
    if (!logoFile) { setLogoPreview(null); return; }
    const url = URL.createObjectURL(logoFile);
    setLogoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [logoFile]);

  const displayedLogo = useMemo(
    () => logoPreview ?? absoluteMediaUrl(settings.logo),
    [logoPreview, settings.logo],
  );

  /* ─── Auto-dismiss the toast ──────────────────────────────────────────── */
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  /* ─── Warn on tab unload if there are unsaved edits ───────────────────── */
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);

  /* ─── Helpers ─────────────────────────────────────────────────────────── */
  const update = <K extends keyof TenantSettings>(key: K, value: TenantSettings[K]) => {
    setSettings((s) => ({ ...s, [key]: value }));
    setDirty(true);
  };

  const onLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLogoFile(e.target.files?.[0] ?? null);
    setDirty(true);
  };
  const clearLogo = () => {
    setLogoFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  /* ─── Save: multipart PATCH covering every tab in one round-trip ─────── */
  const onSave = async () => {
    if (saving) return;
    setSaving(true);
    setToast(null);

    const fd = new FormData();
    // Store & receipt
    fd.append('name',                 settings.name);
    fd.append('phone',                settings.phone);
    fd.append('address',              settings.address);
    fd.append('vat_number',           settings.vat_number);
    fd.append('receipt_footer',       settings.receipt_footer);
    fd.append('show_tax_on_receipt',  settings.show_tax_on_receipt ? 'true' : 'false');
    if (logoFile) fd.append('logo', logoFile);

    // Localization
    fd.append('currency', settings.currency);
    fd.append('language', settings.language);
    fd.append('timezone', settings.timezone);

    // Hardware: printer
    fd.append('printer_name',       settings.printer_name);
    fd.append('printer_connection', settings.printer_connection);
    if (settings.printer_ip) fd.append('printer_ip', settings.printer_ip);
    else                     fd.append('printer_ip', '');

    // Hardware: scale
    fd.append('scale_barcode_prefix',  settings.scale_barcode_prefix);
    fd.append('scale_connection',      settings.scale_connection);
    fd.append('scale_export_interval', settings.scale_export_interval);

    // Payments
    fd.append('payment_cash_enabled',   settings.payment_cash_enabled   ? 'true' : 'false');
    fd.append('payment_card_enabled',   settings.payment_card_enabled   ? 'true' : 'false');
    fd.append('payment_wallet_enabled', settings.payment_wallet_enabled ? 'true' : 'false');
    fd.append('card_terminal_type',     settings.card_terminal_type);

    try {
      const { data } = await apiClient.patch<TenantSettings>(SETTINGS_ENDPOINT, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSettings({ ...EMPTY_TENANT, ...data, logo: data.logo ?? null });
      // Push fields that affect the rest of the app (currency, prefix, logo,
      // receipt-affecting bits) into the auth store so other pages react
      // immediately without a re-login.
      updateUser({
        tenant_name:                 data.name,
        tenant_phone:                data.phone ?? '',
        tenant_address:              data.address ?? '',
        tenant_vat_number:           data.vat_number ?? '',
        tenant_receipt_footer:       data.receipt_footer ?? '',
        tenant_currency:             data.currency ?? 'EGP',
        tenant_language:             data.language ?? 'en',
        tenant_show_tax_on_receipt:  data.show_tax_on_receipt ?? true,
        tenant_logo:                 data.logo ?? '',
        tenant_scale_barcode_prefix: data.scale_barcode_prefix ?? '21',
      });
      clearLogo();
      setDirty(false);
      setToast({ kind: 'success', msg: t('settings.saved') });
    } catch (err) {
      let msg = t('settings.saveFailed');
      if (err instanceof AxiosError) {
        const data = err.response?.data as Record<string, unknown> | undefined;
        if (typeof data?.detail === 'string') msg = data.detail;
        else if (data && typeof data === 'object') {
          const first = Object.entries(data)[0];
          if (first) {
            const [field, value] = first;
            const text = Array.isArray(value) ? String(value[0]) : String(value);
            msg = field === 'non_field_errors' ? text : `${field}: ${text}`;
          }
        } else if (err.response?.status === 403) {
          msg = 'You do not have permission to update tenant settings.';
        }
      }
      setToast({ kind: 'error', msg });
    } finally {
      setSaving(false);
    }
  };

  /* ─── Tab renderers ───────────────────────────────────────────────────── */
  const renderStoreTab = () => (
    <Card className="p-6 space-y-5">
      <Field label={t('settings.store.name')}>
        <SettingsInput
          value={settings.name}
          onChange={(e) => update('name', e.target.value)}
          disabled={loading}
        />
      </Field>

      <Field label={t('settings.store.address')}>
        <SettingsInput
          value={settings.address}
          onChange={(e) => update('address', e.target.value)}
          disabled={loading}
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label={t('settings.store.vatNumber')}>
          <SettingsInput
            value={settings.vat_number}
            onChange={(e) => update('vat_number', e.target.value)}
            disabled={loading}
            className="font-mono"
          />
        </Field>
        <Field label={t('settings.store.phones')} hint={t('settings.store.phonesHint')}>
          <SettingsInput
            value={settings.phone}
            onChange={(e) => update('phone', e.target.value)}
            disabled={loading}
            className="font-mono"
            maxLength={255}
          />
        </Field>
      </div>

      <Field label={t('settings.store.footerText')} hint={t('settings.store.footerTextHint')}>
        <textarea
          value={settings.receipt_footer}
          onChange={(e) => update('receipt_footer', e.target.value)}
          disabled={loading}
          rows={3}
          className="w-full px-3 py-2 rounded-md border border-neutral-300 focus-ring bg-white text-[14px] resize-none"
        />
      </Field>

      <ToggleRow
        label={t('settings.store.showVat')}
        hint={t('settings.store.showVatHint')}
        checked={settings.show_tax_on_receipt}
        onChange={(v) => update('show_tax_on_receipt', v)}
        disabled={loading}
      />

      <Field label={t('settings.store.logo')} hint={t('settings.store.logoHint')}>
        <div className="flex items-center gap-4">
          <div className="w-24 h-24 rounded-md border border-neutral-300 bg-neutral-50 grid place-items-center overflow-hidden">
            {displayedLogo ? (
              <img src={displayedLogo} alt="Logo preview" className="max-w-full max-h-full object-contain" />
            ) : (
              <Icon name="receipt" size={28} className="text-neutral-400" />
            )}
          </div>
          <div className="flex-1 flex flex-col gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={onLogoChange}
              disabled={loading}
              className="text-[12px]"
            />
            {logoFile && (
              <button
                type="button"
                onClick={clearLogo}
                className="self-start text-[12px] text-danger-600 hover:underline focus-ring"
              >
                {t('settings.store.removeFile')}
              </button>
            )}
          </div>
        </div>
      </Field>
    </Card>
  );

  const renderHardwareTab = () => (
    <div className="space-y-4">
      <Card className="p-6 space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-neutral-200">
          <div className="w-8 h-8 rounded-md bg-brand-50 text-brand-600 grid place-items-center">
            <Icon name="printer" size={18} />
          </div>
          <h3 className="text-[15px] font-semibold">{t('settings.hardware.printer')}</h3>
        </div>

        <Field label={t('settings.hardware.printerName')}>
          <SettingsInput
            value={settings.printer_name}
            onChange={(e) => update('printer_name', e.target.value)}
            placeholder="e.g. Star TSP143III"
            disabled={loading}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label={t('settings.hardware.connection')}>
            <SettingsSelect
              value={settings.printer_connection}
              onChange={(e) => update('printer_connection', e.target.value as TenantSettings['printer_connection'])}
              disabled={loading}
            >
              <option value="usb">USB</option>
              <option value="network">Network</option>
              <option value="bluetooth">Bluetooth</option>
            </SettingsSelect>
          </Field>

          <Field label={t('settings.hardware.ipAddress')} hint={t('settings.hardware.ipHint')}>
            <SettingsInput
              value={settings.printer_ip ?? ''}
              onChange={(e) => update('printer_ip', e.target.value || null)}
              disabled={loading || settings.printer_connection !== 'network'}
              placeholder="192.168.1.42"
              className="font-mono"
            />
          </Field>
        </div>

        <Button variant="secondary" size="md" type="button" onClick={() => window.print()}>
          <Icon name="printer" size={16} /> {t('settings.hardware.testPrint')}
        </Button>
      </Card>

      <Card className="p-6 space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-neutral-200">
          <div className="w-8 h-8 rounded-md bg-brand-50 text-brand-600 grid place-items-center">
            <Icon name="barcode" size={18} />
          </div>
          <h3 className="text-[15px] font-semibold">{t('settings.hardware.scale')}</h3>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label={t('settings.hardware.barcodePrefix')} hint={t('settings.hardware.barcodePrefixHint')}>
            <SettingsInput
              value={settings.scale_barcode_prefix}
              onChange={(e) => update('scale_barcode_prefix', e.target.value.replace(/\D/g, '').slice(0, 4))}
              disabled={loading}
              maxLength={4}
              className="font-mono w-24"
            />
          </Field>

          <Field label={t('settings.hardware.connection')}>
            <SettingsSelect
              value={settings.scale_connection}
              onChange={(e) => update('scale_connection', e.target.value as TenantSettings['scale_connection'])}
              disabled={loading}
            >
              <option value="serial">Serial</option>
              <option value="usb">USB</option>
              <option value="network">Network</option>
            </SettingsSelect>
          </Field>
        </div>

        <Field label={t('settings.hardware.exportInterval')} hint={t('settings.hardware.exportIntervalHint')}>
          <SettingsSelect
            value={settings.scale_export_interval}
            onChange={(e) => update('scale_export_interval', e.target.value as TenantSettings['scale_export_interval'])}
            disabled={loading}
          >
            <option value="manual">Manual</option>
            <option value="hourly">Hourly</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </SettingsSelect>
        </Field>
      </Card>
    </div>
  );

  const renderPaymentsTab = () => (
    <Card className="p-6 space-y-3">
      <div className="text-[12px] text-neutral-500 uppercase tracking-wider font-semibold">
        {t('settings.payments.acceptedMethods')}
      </div>
      <ToggleRow
        label={t('settings.payments.cash')}
        checked={settings.payment_cash_enabled}
        onChange={(v) => update('payment_cash_enabled', v)}
        disabled={loading}
      />
      <ToggleRow
        label={t('settings.payments.card')}
        checked={settings.payment_card_enabled}
        onChange={(v) => update('payment_card_enabled', v)}
        disabled={loading}
      />
      <ToggleRow
        label={t('settings.payments.wallet')}
        hint={t('settings.payments.walletHint')}
        checked={settings.payment_wallet_enabled}
        onChange={(v) => update('payment_wallet_enabled', v)}
        disabled={loading}
      />

      <div className="pt-4 border-t border-neutral-200">
        <Field label={t('settings.payments.terminalType')} hint={t('settings.payments.terminalHint')}>
          <SettingsSelect
            value={settings.card_terminal_type}
            onChange={(e) => update('card_terminal_type', e.target.value)}
            disabled={loading || !settings.payment_card_enabled}
          >
            <option value="">{t('common.none')}</option>
            <option value="PAX A920">PAX A920</option>
            <option value="Ingenico Move/5000">Ingenico Move/5000</option>
            <option value="Verifone V200c">Verifone V200c</option>
          </SettingsSelect>
        </Field>
      </div>
    </Card>
  );

  const renderLocalizationTab = () => (
    <Card className="p-6 grid grid-cols-3 gap-4">
      <Field label={t('settings.localization.language')}>
        <SettingsSelect
          value={settings.language}
          onChange={(e) => update('language', e.target.value)}
          disabled={loading}
        >
          <option value="en">English</option>
          <option value="ar">العربية</option>
        </SettingsSelect>
      </Field>
      <Field label={t('settings.localization.currency')} hint={t('settings.localization.currencyHint')}>
        <SettingsSelect
          value={settings.currency}
          onChange={(e) => update('currency', e.target.value)}
          disabled={loading}
        >
          <option value="EGP">EGP</option>
          <option value="EUR">EUR</option>
          <option value="USD">USD</option>
          <option value="SAR">SAR</option>
          <option value="AED">AED</option>
        </SettingsSelect>
      </Field>
      <Field label={t('settings.localization.timezone')}>
        <SettingsSelect
          value={settings.timezone}
          onChange={(e) => update('timezone', e.target.value)}
          disabled={loading}
        >
          <option value="Africa/Cairo">Africa/Cairo</option>
          <option value="Asia/Riyadh">Asia/Riyadh</option>
          <option value="Asia/Dubai">Asia/Dubai</option>
          <option value="Europe/Madrid">Europe/Madrid</option>
          <option value="Europe/London">Europe/London</option>
          <option value="UTC">UTC</option>
        </SettingsSelect>
      </Field>
    </Card>
  );

  const renderTranslationsTab = () => (
    <TranslationsManager
      tenantLanguage={(settings.language as SupportedLanguage) ?? 'en'}
      onToast={setToast}
    />
  );

  const renderSubscriptionTab = () => (
    <SubscriptionPanel plan={settings.plan} trialEndsAt={settings.trial_ends_at} />
  );

  const renderBranchesTab = () => <BranchesPanel onToast={setToast} />;

  const tabBody = (() => {
    switch (activeTab) {
      case 'store':        return renderStoreTab();
      case 'hardware':     return renderHardwareTab();
      case 'payments':     return renderPaymentsTab();
      case 'localization': return renderLocalizationTab();
      case 'translations': return renderTranslationsTab();
      case 'subscription': return renderSubscriptionTab();
      case 'branches':     return renderBranchesTab();
    }
  })();

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <Header
        title={t('settings.title')}
        subtitle={t('settings.subtitle')}
        right={
          <div className="flex items-center gap-3">
            {dirty && !saving && (
              <span className="text-[12px] font-semibold text-warn-700 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-warn-500" />
                {t('common.unsavedChanges')}
              </span>
            )}
            <Button size="sm" onClick={onSave} disabled={saving || loading || !dirty}>
              {saving ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full spin" />
                  {t('common.saving')}
                </>
              ) : (
                <>{t('common.saveAllChanges')}</>
              )}
            </Button>
          </div>
        }
      />

      {toast && (
        <div
          role={toast.kind === 'success' ? 'status' : 'alert'}
          className={`mx-6 mt-4 rounded-md border px-3 py-2.5 text-[13px] flex items-start gap-2 ${
            toast.kind === 'success'
              ? 'border-success-500/30 bg-success-50 text-success-700'
              : 'border-danger-500/30 bg-danger-50 text-danger-700'
          }`}
        >
          <Icon name={toast.kind === 'success' ? 'check' : 'alert'} size={16} className="mt-0.5 shrink-0" />
          <span className="flex-1">{toast.msg}</span>
          <button onClick={() => setToast(null)} className="shrink-0 hover:opacity-70 focus-ring rounded" aria-label={t('common.dismiss')}>
            <Icon name="x" size={14} />
          </button>
        </div>
      )}

      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* ── Left rail: tabs ─────────────────────────────────────────────── */}
        <nav className="w-64 shrink-0 border-e border-neutral-200 bg-white px-3 py-5 overflow-y-auto">
          <ul className="space-y-1">
            {TABS.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <li key={tab.id}>
                  <button
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full flex items-center gap-3 px-3 h-10 rounded-md text-[14px] font-medium focus-ring transition
                      ${isActive
                        ? 'bg-brand-50 text-brand-700 font-semibold'
                        : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
                      }`}
                  >
                    <span aria-hidden className="text-[16px]">{tab.emoji}</span>
                    <span className="flex-1 text-start">{t(tab.labelKey)}</span>
                    {isActive && <Icon name="chevR" size={14} />}
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="mt-6 px-3 text-[11.5px] text-neutral-500 leading-relaxed">
            {t('settings.tabsHint')}
          </div>
        </nav>

        {/* ── Right pane: active tab content ──────────────────────────────── */}
        <div className="flex-1 min-h-0 overflow-auto p-6 max-w-[900px]">
          {tabBody}
        </div>
      </div>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────────
 * Translations tab — manages per-tenant override JSON dicts per language.
 *
 * Endpoints:
 *   GET    /accounts/tenant/translations/<lang>/
 *   PUT    /accounts/tenant/translations/<lang>/   (JSON body OR multipart `file`)
 *   DELETE /accounts/tenant/translations/<lang>/
 * ──────────────────────────────────────────────────────────────────────────── */

interface OverrideResponse {
  language:  SupportedLanguage;
  overrides: Record<string, unknown>;
  count:     number;
}

const downloadJson = (filename: string, payload: unknown) => {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

const TranslationsManager: React.FC<{
  tenantLanguage: SupportedLanguage;
  onToast: (t: { kind: 'success' | 'error'; msg: string }) => void;
}> = ({ tenantLanguage, onToast }) => {
  const { t } = useTranslation();
  const [lang, setLang] = useState<SupportedLanguage>(tenantLanguage);
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const fileRef = useRef<HTMLInputElement | null>(null);

  /* Load overrides whenever the picker changes. */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<OverrideResponse>(`/accounts/tenant/translations/${lang}/`)
      .then((resp) => {
        if (cancelled) return;
        setOverrides(resp.data.overrides ?? {});
        setCount(resp.data.count ?? 0);
      })
      .catch(() => {
        if (cancelled) return;
        setOverrides({});
        setCount(0);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [lang]);

  const onDownloadTemplate = () => {
    downloadJson(`translations_${lang}_template.json`, getBundledTranslations(lang));
  };

  const onUploadClick = () => fileRef.current?.click();

  const onFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const text = await file.text();
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch {
        onToast({ kind: 'error', msg: t('settings.translations.invalidJson') });
        return;
      }

      const fd = new FormData();
      fd.append('file', file);
      const { data } = await apiClient.put<OverrideResponse>(
        `/accounts/tenant/translations/${lang}/`,
        fd,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      setOverrides(data.overrides);
      setCount(data.count);
      applyTenantOverrides(lang, data.overrides);
      onToast({ kind: 'success', msg: t('settings.translations.uploadSuccess', { count: data.count }) });
      void parsed;   // parsed is only used for the early invalid-JSON check above
    } catch (err) {
      let msg = t('settings.translations.uploadFailed');
      if (err instanceof AxiosError) {
        const data = err.response?.data as Record<string, unknown> | undefined;
        if (typeof data?.detail === 'string') msg = data.detail;
      }
      onToast({ kind: 'error', msg });
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const onReset = async () => {
    if (!confirm(t('settings.translations.resetConfirm'))) return;
    setBusy(true);
    try {
      await apiClient.delete(`/accounts/tenant/translations/${lang}/`);
      setOverrides({});
      setCount(0);
      applyTenantOverrides(lang, {});
      onToast({ kind: 'success', msg: t('settings.translations.resetSuccess') });
    } catch {
      onToast({ kind: 'error', msg: t('settings.translations.uploadFailed') });
    } finally {
      setBusy(false);
    }
  };

  // Flatten the overrides into ["key.path", "value"] pairs for the preview.
  const previewRows = useMemo(() => {
    const rows: { key: string; value: string }[] = [];
    const walk = (obj: Record<string, unknown>, prefix: string) => {
      for (const [k, v] of Object.entries(obj)) {
        const full = prefix ? `${prefix}.${k}` : k;
        if (v && typeof v === 'object' && !Array.isArray(v)) {
          walk(v as Record<string, unknown>, full);
        } else {
          rows.push({ key: full, value: String(v) });
        }
      }
    };
    walk(overrides, '');
    rows.sort((a, b) => a.key.localeCompare(b.key));
    return rows;
  }, [overrides]);

  return (
    <Card className="p-6 space-y-5">
      <div>
        <h3 className="text-[15px] font-semibold">{t('settings.translations.title')}</h3>
        <p className="text-[12.5px] text-neutral-500 mt-1 leading-relaxed">
          {t('settings.translations.subtitle')}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 items-end">
        <Field label={t('settings.translations.language')}>
          <SettingsSelect
            value={lang}
            onChange={(e) => setLang(e.target.value as SupportedLanguage)}
            disabled={busy}
          >
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>{code === 'ar' ? 'العربية (ar)' : `English (${code})`}</option>
            ))}
          </SettingsSelect>
        </Field>
        <div className="text-[13px] text-neutral-600">
          <span className="font-semibold">{t('settings.translations.currentOverrides')}: </span>
          <span className="font-mono">{loading ? '…' : count}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Button type="button" variant="secondary" size="md" onClick={onDownloadTemplate} disabled={busy}>
            <Icon name="archive" size={16} /> {t('settings.translations.downloadTemplate')}
          </Button>
          <div className="text-[11.5px] text-neutral-500 mt-1.5">
            {t('settings.translations.downloadTemplateHint')}
          </div>
        </div>
        <div>
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            onChange={onFileChosen}
            className="hidden"
          />
          <Button type="button" size="md" onClick={onUploadClick} disabled={busy}>
            <Icon name="plus" size={16} /> {t('settings.translations.uploadFile')}
          </Button>
          <div className="text-[11.5px] text-neutral-500 mt-1.5">
            {t('settings.translations.uploadFileHint')}
          </div>
        </div>
      </div>

      {count > 0 && (
        <div className="pt-2">
          <Button type="button" variant="secondary" size="sm" onClick={onReset} disabled={busy}>
            <Icon name="trash" size={14} /> {t('settings.translations.reset')}
          </Button>
        </div>
      )}

      {/* Preview */}
      <div className="border-t border-neutral-200 pt-4">
        <div className="text-[12px] font-semibold uppercase tracking-wider text-neutral-500 mb-2">
          {t('settings.translations.previewHeader', { count })}
        </div>
        {previewRows.length === 0 ? (
          <div className="text-[13px] text-neutral-500 py-6 text-center">
            {t('settings.translations.noOverrides')}
          </div>
        ) : (
          <div className="border border-neutral-200 rounded-md overflow-hidden max-h-[320px] overflow-y-auto">
            <table className="w-full text-[13px]">
              <thead className="bg-neutral-50 text-[11px] uppercase tracking-wider text-neutral-500">
                <tr>
                  <th className="px-3 py-2 text-start font-semibold w-1/2">Key</th>
                  <th className="px-3 py-2 text-start font-semibold">Value</th>
                </tr>
              </thead>
              <tbody>
                {previewRows.map((row) => (
                  <tr key={row.key} className="border-t border-neutral-100">
                    <td className="px-3 py-1.5 font-mono text-[12px] text-neutral-700">{row.key}</td>
                    <td className="px-3 py-1.5 text-neutral-800">{row.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
};

/* ─────────────────────────────────────────────────────────────────────────────
 * Subscription panel — read-only view of the tenant's plan + trial expiry.
 * Visual severity follows daysRemaining bands.
 * ──────────────────────────────────────────────────────────────────────────── */
const SubscriptionPanel: React.FC<{
  plan: TenantSettings['plan'];
  trialEndsAt: string | null;
}> = ({ plan, trialEndsAt }) => {
  const { t, i18n } = useTranslation();

  // Compute days remaining + severity band. `null` trial_ends_at = unknown.
  const { daysRemaining, severity, formattedDate } = useMemo(() => {
    if (!trialEndsAt) {
      return { daysRemaining: null as number | null, severity: 'unknown' as const, formattedDate: '' };
    }
    const expiry = new Date(trialEndsAt);
    if (Number.isNaN(expiry.getTime())) {
      return { daysRemaining: null, severity: 'unknown' as const, formattedDate: trialEndsAt };
    }
    const days = differenceInDays(startOfDay(expiry), startOfDay(new Date()));
    let band: 'healthy' | 'soon' | 'critical' | 'expired';
    if (days < 0)       band = 'expired';
    else if (days <= 3) band = 'critical';
    else if (days <= 14) band = 'soon';
    else                band = 'healthy';

    const fmt = format(expiry, 'PP', { locale: i18n.language === 'ar' ? ar : enUS });
    return { daysRemaining: days, severity: band, formattedDate: fmt };
  }, [trialEndsAt, i18n.language]);

  // Tailwind class buckets. Each band uses the spec'd green/orange/red tokens.
  const palette = (() => {
    switch (severity) {
      case 'healthy':
        return { box: 'bg-green-100 text-green-800 border-green-200', label: 'text-green-700', dot: 'bg-green-500', statusKey: 'settings.subscription.active' };
      case 'soon':
        return { box: 'bg-orange-100 text-orange-800 border-orange-200', label: 'text-orange-700', dot: 'bg-orange-500', statusKey: 'settings.subscription.expiringSoon' };
      case 'critical':
        return { box: 'bg-red-100 text-red-800 border-red-200',       label: 'text-red-700',    dot: 'bg-red-500',    statusKey: 'settings.subscription.critical' };
      case 'expired':
        return { box: 'bg-red-100 text-red-900 border-red-300',       label: 'text-red-800',    dot: 'bg-red-600',    statusKey: 'settings.subscription.expired' };
      default:
        return { box: 'bg-neutral-100 text-neutral-700 border-neutral-200', label: 'text-neutral-600', dot: 'bg-neutral-400', statusKey: 'settings.subscription.active' };
    }
  })();

  const planLabel = t(`settings.subscription.plan.${plan}`, { defaultValue: plan });

  const daysText = daysRemaining == null
    ? null
    : daysRemaining < 0
      ? t('settings.subscription.expiredOn', { date: formattedDate })
      : t('settings.subscription.daysRemaining', { count: daysRemaining });

  return (
    <Card className="p-6 space-y-6">
      <div>
        <h3 className="text-[15px] font-semibold">{t('settings.subscription.title')}</h3>
        <p className="text-[12.5px] text-neutral-500 mt-1">{t('settings.subscription.subtitle')}</p>
      </div>

      {/* Plan + status row */}
      <div className="grid grid-cols-2 gap-4">
        <div className="border border-neutral-200 rounded-md p-4">
          <div className="text-[11px] uppercase tracking-wider font-semibold text-neutral-500 mb-2">
            {t('settings.subscription.currentPlan')}
          </div>
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-100 text-brand-800 text-[14px] font-semibold">
            💎 {planLabel}
          </span>
        </div>

        <div className={`border rounded-md p-4 ${palette.box}`}>
          <div className="text-[11px] uppercase tracking-wider font-semibold opacity-80 mb-2">
            {t('settings.subscription.status')}
          </div>
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${palette.dot}`} />
            <span className="text-[14px] font-semibold">{t(palette.statusKey)}</span>
          </div>
        </div>
      </div>

      {/* Renewal date row */}
      <div className="border border-neutral-200 rounded-md p-4">
        <div className="text-[11px] uppercase tracking-wider font-semibold text-neutral-500 mb-2">
          {t('settings.subscription.expiryDate')}
        </div>
        {trialEndsAt ? (
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="text-[15px] font-semibold text-neutral-800">{formattedDate}</div>
            {daysText && (
              <div className={`text-[13px] font-semibold ${palette.label}`}>
                {daysText}
              </div>
            )}
          </div>
        ) : (
          <div className="text-[13px] text-neutral-500 italic">
            {t('settings.subscription.noTrial')}
          </div>
        )}
      </div>

      {/* Severity-coded warning band */}
      {severity === 'soon' && (
        <div className="rounded-md border border-orange-200 bg-orange-50 text-orange-800 px-4 py-3 text-[13px]">
          {t('settings.subscription.warningSoon')}
        </div>
      )}
      {severity === 'critical' && daysRemaining != null && (
        <div className="rounded-md border-2 border-red-300 bg-red-50 text-red-800 px-4 py-3 text-[14px] font-semibold">
          {t('settings.subscription.warningCritical', { count: daysRemaining })}
        </div>
      )}
      {severity === 'expired' && (
        <div className="rounded-md border-2 border-red-400 bg-red-50 text-red-900 px-4 py-3 text-[14px] font-semibold">
          {t('settings.subscription.warningExpired')}
        </div>
      )}

      <div className="pt-2 flex justify-start">
        <Button
          type="button"
          size="md"
          onClick={() => window.open('mailto:support@superpos.io?subject=Subscription%20renewal', '_blank')}
        >
          {t('settings.subscription.renew')}
        </Button>
      </div>
    </Card>
  );
};

/* ─────────────────────────────────────────────────────────────────────────────
 * Branches panel — read-only card grid over GET /accounts/branches/
 * ──────────────────────────────────────────────────────────────────────────── */
interface BranchDto {
  id: number;
  name: string;
  address: string;
  phone: string;
  active: boolean;
  created_at?: string;
}

const BranchesPanel: React.FC<{ onToast: (t: { kind: 'success' | 'error'; msg: string }) => void }> = ({ onToast }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState<BranchDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<BranchDto[] | { results: BranchDto[] }>('/accounts/branches/')
      .then((resp) => {
        if (cancelled) return;
        const data = resp.data;
        setItems(Array.isArray(data) ? data : (data.results ?? []));
      })
      .catch(() => {
        if (cancelled) return;
        const msg = t('settings.branches.loadFailed');
        setError(msg);
        onToast({ kind: 'error', msg });
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Card className="p-6 space-y-5">
      <div>
        <h3 className="text-[15px] font-semibold">{t('settings.branches.title')}</h3>
        <p className="text-[12.5px] text-neutral-500 mt-1">{t('settings.branches.subtitle')}</p>
      </div>

      {loading ? (
        <div className="text-[13px] text-neutral-500 py-12 text-center">{t('settings.branches.loading')}</div>
      ) : error ? (
        <div className="text-[13px] text-danger-600 py-12 text-center">{error}</div>
      ) : items.length === 0 ? (
        <div className="text-[13px] text-neutral-500 py-12 text-center">{t('settings.branches.empty')}</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map((branch) => (
            <div key={branch.id} className="border border-neutral-200 rounded-md p-4 hover:border-brand-300 transition">
              <div className="flex items-start justify-between gap-2 mb-3">
                <h4 className="font-bold text-[15px] text-neutral-900">{branch.name}</h4>
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11.5px] font-semibold whitespace-nowrap
                    ${branch.active
                      ? 'bg-green-100 text-green-700 border border-green-200'
                      : 'bg-neutral-200 text-neutral-600 border border-neutral-300'
                    }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${branch.active ? 'bg-green-500' : 'bg-neutral-400'}`} />
                  {branch.active ? t('settings.branches.active') : t('settings.branches.inactive')}
                </span>
              </div>

              <div className="space-y-1.5 text-[13px] text-neutral-700">
                <div className="flex items-start gap-2">
                  <span aria-hidden className="shrink-0">📞</span>
                  <span className={branch.phone ? 'font-mono' : 'text-neutral-400 italic'}>
                    {branch.phone || t('settings.branches.noPhone')}
                  </span>
                </div>
                <div className="flex items-start gap-2">
                  <span aria-hidden className="shrink-0">📍</span>
                  <span className={branch.address ? '' : 'text-neutral-400 italic'}>
                    {branch.address || t('settings.branches.noAddress')}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="pt-2 border-t border-neutral-200 flex items-center justify-between gap-3 flex-wrap">
        <p className="text-[12.5px] text-neutral-500">{t('settings.branches.addHint')}</p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => window.open('mailto:support@superpos.io?subject=Add%20branch', '_blank')}
        >
          {t('settings.branches.contactSupport')}
        </Button>
      </div>
    </Card>
  );
};
