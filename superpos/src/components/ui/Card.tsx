import React from 'react';

interface CardProps {
  className?: string;
  children: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({ className = '', children }) => (
  <div className={`bg-white border border-neutral-200 rounded-lg shadow-sm ${className}`}>
    {children}
  </div>
);

/** 52px card header row: title left, optional actions right (prototype `.card-h`). */
export const CardHeader: React.FC<{
  title: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}> = ({ title, actions, className = '' }) => (
  <div className={`h-[52px] px-4 flex items-center justify-between border-b border-neutral-200 ${className}`}>
    <span className="text-[14px] font-bold">{title}</span>
    {actions}
  </div>
);

export const CardBody: React.FC<CardProps> = ({ className = '', children }) => (
  <div className={`p-4 ${className}`}>{children}</div>
);
