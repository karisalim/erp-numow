import React, { useRef, useEffect } from 'react';
import { Icon } from '../ui/Icon';

interface BarcodeInputProps {
  value: string;
  setValue: (v: string) => void;
  onSubmit: (value: string) => void;
  error: boolean;
}

export const BarcodeInput: React.FC<BarcodeInputProps> = ({ value, setValue, onSubmit, error }) => {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const handler = (e: Event) => {
      const tag = ((e.target as HTMLElement)?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'button') {
        clearTimeout(timer);
        timer = setTimeout(() => ref.current?.focus(), 1500);
      }
    };
    document.addEventListener('click', handler);
    document.addEventListener('focusin', handler);
    return () => {
      document.removeEventListener('click', handler);
      document.removeEventListener('focusin', handler);
      clearTimeout(timer);
    };
  }, []);

  return (
    <div
      className={`relative rounded-lg border-2 transition-colors
        ${error ? 'border-danger-500 bg-danger-50' : 'border-brand-500 bg-white'}`}
    >
      <div className="absolute start-4 top-1/2 -translate-y-1/2 text-brand-500 pointer-events-none">
        <Icon name="barcode" size={24} />
      </div>
      <input
        ref={ref}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter') {
            e.preventDefault();
            onSubmit(value);
          }
        }}
        placeholder="Scan or type barcode…"
        className="w-full h-14 ps-14 pe-32 text-[20px] font-mono tracking-wider bg-transparent focus:outline-none"
        spellCheck={false}
        autoComplete="off"
        aria-label="Barcode scanner input"
      />
      <span className="absolute end-4 top-1/2 -translate-y-1/2 flex items-center gap-2 text-[12px] text-neutral-500">
        <span className="caret" aria-hidden />
        <kbd className="px-2 py-0.5 rounded border border-neutral-300 bg-neutral-50 font-mono text-[11px]">Enter</kbd>
      </span>
    </div>
  );
};
