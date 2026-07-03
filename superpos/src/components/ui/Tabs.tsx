import React from 'react';

/** Chip-style tab row (prototype settings tabs). */
export interface TabOption<V extends string = string> {
  value: V;
  label: string;
}

export function Tabs<V extends string>({
  options,
  value,
  onChange,
  className = '',
}: {
  options: TabOption<V>[];
  value: V;
  onChange: (v: V) => void;
  className?: string;
}) {
  return (
    <div role="tablist" className={`flex items-center gap-1.5 flex-wrap ${className}`}>
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={`h-[32px] px-3.5 rounded-md text-[13px] font-semibold transition-colors focus-ring
            ${value === o.value
              ? 'bg-white text-neutral-900 shadow-sm border border-neutral-200'
              : 'text-neutral-500 hover:bg-neutral-100 border border-transparent'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
