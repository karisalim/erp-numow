import React from 'react';
import { Icon } from './Icon';

/**
 * KPI card following the prototype `.kpi` style: 12px label, large bold
 * value, optional sub-line and icon chip.
 */
export const StatCard: React.FC<{
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  subClassName?: string;
  icon?: string;
  iconBg?: string;   // tailwind bg class for the icon chip
  className?: string;
}> = ({ label, value, sub, subClassName = 'text-neutral-500', icon, iconBg = 'bg-brand-600', className = '' }) => (
  <div className={`bg-white border border-neutral-200 rounded-lg shadow-sm p-4 ${className}`}>
    <div className="flex items-start justify-between">
      <div className="text-[12px] text-neutral-500 font-semibold">{label}</div>
      {icon && (
        <div className={`w-[30px] h-[30px] rounded-md grid place-items-center text-white ${iconBg}`}>
          <Icon name={icon} size={15} />
        </div>
      )}
    </div>
    <div className="text-[24px] font-extrabold tracking-tight mt-1.5 tabular-nums">{value}</div>
    {sub && <div className={`text-[11.5px] mt-0.5 ${subClassName}`}>{sub}</div>}
  </div>
);

/** Responsive KPI grid wrapper (4-up desktop, 2-up tablet, 1-up narrow). */
export const StatCardGrid: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <div className={`grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5 ${className}`}>{children}</div>
);
