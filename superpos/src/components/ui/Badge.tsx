import React from 'react';
import type { BadgeKind } from '../../types';

interface BadgeProps {
  kind?: BadgeKind;
  size?: 'sm' | 'md';
  children: React.ReactNode;
}

const kindClasses: Record<BadgeKind, string> = {
  gray:    'bg-neutral-100 text-neutral-700',
  success: 'bg-success-50 text-success-700',
  danger:  'bg-danger-50 text-danger-700',
  warn:    'bg-warn-50 text-warn-700',
  info:    'bg-[#ECFEFF] text-[#0E7490]',
  brand:   'bg-brand-50 text-brand-700',
};

export const Badge: React.FC<BadgeProps> = ({ kind = 'gray', size = 'sm', children }) => {
  const sizeClass = size === 'md' ? 'px-3 py-1 text-[12px]' : 'px-2 py-0.5 text-[11px]';
  return (
    <span className={`inline-flex items-center gap-1 rounded ${sizeClass} font-semibold ${kindClasses[kind]}`}>
      {children}
    </span>
  );
};
