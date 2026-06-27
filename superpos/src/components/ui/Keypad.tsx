import React from 'react';

interface KeypadProps {
  onPress: (key: string) => void;
}

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'C', '0', '⌫'];

export const Keypad: React.FC<KeypadProps> = ({ onPress }) => (
  <div className="grid grid-cols-3 gap-2">
    {KEYS.map(k => (
      <button
        key={k}
        onClick={() => onPress(k)}
        className={`h-[60px] rounded-lg font-semibold text-[20px] focus-ring transition-colors
          ${k === 'C'
            ? 'bg-warn-50 text-warn-700 hover:bg-warn-500/20'
            : k === '⌫'
            ? 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
            : 'bg-white border border-neutral-300 hover:border-brand-500 hover:bg-brand-50'
          }`}
      >
        {k}
      </button>
    ))}
  </div>
);
