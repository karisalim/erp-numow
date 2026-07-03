import React from 'react';

/**
 * Horizontal filter row: chip toggles (prototype `.chip` style) plus any
 * extra controls (selects, date inputs) passed as children.
 */
export interface FilterChip<V extends string = string> {
  value: V;
  label: string;
}

export function FilterChips<V extends string>({
  options,
  value,
  onChange,
}: {
  options: FilterChip<V>[];
  value: V;
  onChange: (v: V) => void;
}) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`h-[30px] px-3 rounded-md border text-[12.5px] font-semibold transition-colors focus-ring
            ${value === o.value
              ? 'bg-neutral-900 text-white border-neutral-900'
              : 'bg-white text-neutral-600 border-neutral-300 hover:bg-neutral-50'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const FilterBar: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <div className={`flex items-center gap-3 flex-wrap mb-4 ${className}`}>{children}</div>
);
