import React from 'react';
import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { Icon } from './Icon';

/* ─────────────────────────────────────────────────────────────────────────────
 * Form primitives following the prototype input style: 40px controls,
 * 8px radius, n300 border, blue focus ring, 12.5px semibold labels.
 * Each field owns its label + inline validation error.
 *
 * Phase 3 (Enterprise UX Polish): a single, explicit field-state vocabulary
 * used everywhere a form renders an input — Normal / Focused / Required /
 * Recommended / Valid / Invalid / Disabled / Read-only / Loading / Saving.
 * `Focused` is native `:focus` + the shared `.focus-ring` utility (never
 * re-implemented per field); every other state is driven by the props
 * below, so a form built from these primitives can't drift from another.
 * ──────────────────────────────────────────────────────────────────────────── */

const baseControl =
  'w-full h-10 px-3 rounded-md border text-[14px] text-neutral-900 focus-ring transition-colors';

/** One function, one source of truth for every input/select's border+background
 * across every state — this is what "standardized field states" means in
 * practice: no page picks its own gray/red/green shade. */
function controlState(opts: { error?: string; disabled?: boolean; readOnly?: boolean; valid?: boolean }): string {
  const { error, disabled, readOnly, valid } = opts;
  if (disabled) return 'bg-neutral-100 text-neutral-500 border-neutral-200 cursor-not-allowed';
  if (readOnly) return 'bg-neutral-50 text-neutral-700 border-neutral-200 cursor-default';
  if (error) return 'bg-white border-danger-500';
  if (valid) return 'bg-white border-success-500';
  return 'bg-white border-neutral-300';
}

export const FieldLabel: React.FC<{
  label: string;
  required?: boolean;
  recommended?: boolean;
  htmlFor?: string;
}> = ({ label, required, recommended, htmlFor }) => (
  <label htmlFor={htmlFor} className="flex items-center gap-1 text-[12.5px] font-semibold text-neutral-700 mb-1.5">
    <span>{label}</span>
    {required && <span className="text-danger-500" title="Required — the backend rejects a save without this">*</span>}
    {!required && recommended && (
      <span
        className="text-[10.5px] font-medium text-neutral-400 bg-neutral-100 rounded px-1 py-px normal-case tracking-normal"
        title="Recommended for good data hygiene — not enforced"
      >
        recommended
      </span>
    )}
  </label>
);

export const FieldError: React.FC<{ error?: string }> = ({ error }) =>
  error ? (
    <div className="flex items-center gap-1 text-[12px] text-danger-600 mt-1">
      <Icon name="alert" size={12} />
      {error}
    </div>
  ) : null;

interface FieldChromeProps {
  error?: string;
  hint?: string;
  valid?: boolean;
  loading?: boolean;
}

/** The shared bottom-line: error beats everything, then a loading note,
 * then the plain hint/description — never more than one line shown at once
 * so forms don't jitter in height as state changes. */
const FieldChrome: React.FC<FieldChromeProps> = ({ error, hint, loading }) => {
  if (error) return <FieldError error={error} />;
  if (loading) {
    return (
      <div className="flex items-center gap-1.5 text-[11.5px] text-neutral-400 mt-1">
        <span className="w-2.5 h-2.5 border-2 border-neutral-300 border-t-brand-500 rounded-full spin" />
        Loading…
      </div>
    );
  }
  if (hint) return <div className="text-[11.5px] text-neutral-400 mt-1">{hint}</div>;
  return null;
};

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
  recommended?: boolean;
  /** Show a green border + check once the value is non-empty and valid —
   * opt-in per field (a blank *optional* field is not "invalid", but it's
   * not "confirmed valid" either, so this only lights up where a caller
   * explicitly wants positive confirmation, e.g. Name/Barcode). */
  showValid?: boolean;
  loading?: boolean;
  containerClassName?: string;
}

export const FormField: React.FC<FormFieldProps> = ({
  label,
  error,
  hint,
  required,
  recommended,
  showValid,
  loading,
  containerClassName = '',
  className = '',
  id,
  value,
  disabled,
  readOnly,
  ...props
}) => {
  const fieldId = id ?? `f-${label.replace(/\s+/g, '-').toLowerCase()}`;
  const valid = !!showValid && !error && !!String(value ?? '').trim();
  return (
    <div className={containerClassName}>
      <FieldLabel label={label} required={required} recommended={recommended} htmlFor={fieldId} />
      <div className="relative">
        <input
          id={fieldId}
          required={required}
          disabled={disabled}
          readOnly={readOnly}
          value={value}
          className={`${baseControl} ${controlState({ error, disabled, readOnly, valid })} ${valid ? 'pe-8' : ''} ${className}`}
          {...props}
        />
        {valid && (
          <span className="absolute inset-y-0 end-2.5 flex items-center text-success-500 pointer-events-none">
            <Icon name="check" size={14} />
          </span>
        )}
      </div>
      <FieldChrome error={error} hint={hint} loading={loading} />
    </div>
  );
};

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
  hint?: string;
  recommended?: boolean;
  loading?: boolean;
  containerClassName?: string;
}

export const SelectField: React.FC<SelectFieldProps> = ({
  label,
  error,
  hint,
  required,
  recommended,
  loading,
  containerClassName = '',
  className = '',
  children,
  id,
  disabled,
  ...props
}) => {
  const fieldId = id ?? `s-${label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className={containerClassName}>
      <FieldLabel label={label} required={required} recommended={recommended} htmlFor={fieldId} />
      <select
        id={fieldId}
        required={required}
        disabled={disabled || loading}
        className={`${baseControl} ${controlState({ error, disabled: disabled || loading })} ${className}`}
        {...props}
      >
        {children}
      </select>
      <FieldChrome error={error} hint={hint} loading={loading} />
    </div>
  );
};

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  error?: string;
  hint?: string;
  recommended?: boolean;
  containerClassName?: string;
}

export const TextAreaField: React.FC<TextAreaFieldProps> = ({
  label,
  error,
  hint,
  required,
  recommended,
  containerClassName = '',
  className = '',
  id,
  disabled,
  readOnly,
  ...props
}) => {
  const fieldId = id ?? `t-${label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className={containerClassName}>
      <FieldLabel label={label} required={required} recommended={recommended} htmlFor={fieldId} />
      <textarea
        id={fieldId}
        required={required}
        disabled={disabled}
        readOnly={readOnly}
        className={`w-full px-3 py-2 rounded-md border text-[14px] focus-ring min-h-[72px] ${controlState({ error, disabled, readOnly })} ${className}`}
        {...props}
      />
      <FieldChrome error={error} hint={hint} />
    </div>
  );
};

/* ── SearchField — debounced search input with icon ─────────────────────── */

export const SearchField: React.FC<{
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  autoFocus?: boolean;
}> = ({ value, onChange, placeholder = 'Search…', className = '', autoFocus }) => (
  <div className={`relative ${className}`}>
    <span className="absolute inset-y-0 start-3 flex items-center text-neutral-400 pointer-events-none">
      <Icon name="search" size={16} />
    </span>
    <input
      type="search"
      value={value}
      autoFocus={autoFocus}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full h-10 ps-9 pe-3 rounded-md border border-neutral-300 bg-white text-[14px] focus-ring"
    />
  </div>
);
