import React from 'react';
import type { ButtonHTMLAttributes } from 'react';
import type { ButtonVariant, ButtonSize } from '../../types';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-[13px]',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-5 text-base',
  xl: 'h-14 px-6 text-base',
};

const variantClasses: Record<ButtonVariant, string> = {
  primary:   'bg-brand-500 text-white hover:bg-brand-600 active:bg-brand-700 disabled:bg-neutral-300 disabled:text-neutral-500',
  secondary: 'bg-white text-brand-600 border border-neutral-300 hover:bg-neutral-50 active:bg-neutral-100',
  tertiary:  'bg-transparent text-brand-600 hover:bg-brand-50',
  ghost:     'bg-transparent text-neutral-600 hover:bg-neutral-100',
  danger:    'bg-danger-500 text-white hover:bg-danger-600 active:bg-danger-700',
  success:   'bg-success-500 text-white hover:bg-success-600 active:bg-success-700',
  dark:      'bg-neutral-900 text-white hover:bg-neutral-800',
};

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  ...props
}) => {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-colors focus-ring disabled:cursor-not-allowed ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
};
