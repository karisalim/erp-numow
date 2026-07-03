import React from 'react';
import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { Icon } from './Icon';

/* ─────────────────────────────────────────────────────────────────────────────
 * Form primitives following the prototype input style: 40px controls,
 * 8px radius, n300 border, blue focus ring, 12.5px semibold labels.
 * Each field owns its label + inline validation error.
 * ──────────────────────────────────────────────────────────────────────────── */

const control =
  'w-full h-10 px-3 rounded-md border bg-white text-[14px] text-neutral-900 focus-ring disabled:bg-neutral-100 disabled:text-neutral-500';

const borderFor = (error?: string) => (error ? 'border-danger-500' : 'border-neutral-300');

export const FieldLabel: React.FC<{ label: string; required?: boolean; htmlFor?: string }> = ({
  label,
  required,
  htmlFor,
}) => (
  <label htmlFor={htmlFor} className="block text-[12.5px] font-semibold text-neutral-700 mb-1.5">
    {label}
    {required && <span className="text-danger-500 ms-0.5">*</span>}
  </label>
);

export const FieldError: React.FC<{ error?: string }> = ({ error }) =>
  error ? <div className="text-[12px] text-danger-600 mt-1">{error}</div> : null;

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
  containerClassName?: string;
}

export const FormField: React.FC<FormFieldProps> = ({
  label,
  error,
  hint,
  required,
  containerClassName = '',
  className = '',
  id,
  ...props
}) => {
  const fieldId = id ?? `f-${label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className={containerClassName}>
      <FieldLabel label={label} required={required} htmlFor={fieldId} />
      <input id={fieldId} required={required} className={`${control} ${borderFor(error)} ${className}`} {...props} />
      {hint && !error && <div className="text-[11.5px] text-neutral-400 mt-1">{hint}</div>}
      <FieldError error={error} />
    </div>
  );
};

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
  hint?: string;
  containerClassName?: string;
}

export const SelectField: React.FC<SelectFieldProps> = ({
  label,
  error,
  hint,
  required,
  containerClassName = '',
  className = '',
  children,
  id,
  ...props
}) => {
  const fieldId = id ?? `s-${label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className={containerClassName}>
      <FieldLabel label={label} required={required} htmlFor={fieldId} />
      <select id={fieldId} required={required} className={`${control} ${borderFor(error)} ${className}`} {...props}>
        {children}
      </select>
      {hint && !error && <div className="text-[11.5px] text-neutral-400 mt-1">{hint}</div>}
      <FieldError error={error} />
    </div>
  );
};

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  error?: string;
  containerClassName?: string;
}

export const TextAreaField: React.FC<TextAreaFieldProps> = ({
  label,
  error,
  required,
  containerClassName = '',
  className = '',
  id,
  ...props
}) => {
  const fieldId = id ?? `t-${label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className={containerClassName}>
      <FieldLabel label={label} required={required} htmlFor={fieldId} />
      <textarea
        id={fieldId}
        required={required}
        className={`w-full px-3 py-2 rounded-md border bg-white text-[14px] focus-ring min-h-[72px] ${borderFor(error)} ${className}`}
        {...props}
      />
      <FieldError error={error} />
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
