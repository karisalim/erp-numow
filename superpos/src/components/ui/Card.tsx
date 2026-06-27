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
