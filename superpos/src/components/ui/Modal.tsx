import React, { useEffect } from 'react';
import { Icon } from './Icon';

interface ModalProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: string;
  className?: string;
}

export const Modal: React.FC<ModalProps> = ({
  title,
  onClose,
  children,
  maxWidth = 'max-w-[500px]',
  className = '',
}) => {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[1100] bg-black/50 backdrop-blur-sm grid place-items-center p-6 fade-in"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className={`bg-white rounded-xl shadow-lg w-full ${maxWidth} overflow-hidden ${className}`}>
        <div className="px-6 h-14 border-b border-neutral-200 flex items-center justify-between">
          <h2 className="text-[16px] font-semibold">{title}</h2>
          <button
            onClick={onClose}
            className="w-9 h-9 grid place-items-center rounded-md hover:bg-neutral-100 text-neutral-500 focus-ring"
            aria-label="Close"
          >
            <Icon name="x" size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};
