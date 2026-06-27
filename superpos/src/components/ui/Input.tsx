import React from 'react';
import type { InputHTMLAttributes } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  className?: string;
}

export const Input: React.FC<InputProps> = ({ className = '', ...props }) => (
  <input
    className={`w-full h-10 px-3 rounded-md border border-neutral-300 focus-ring bg-white text-[14px] ${className}`}
    {...props}
  />
);
