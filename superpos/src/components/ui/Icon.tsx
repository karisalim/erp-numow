import React from 'react';

interface IconProps {
  name: string;
  size?: number;
  className?: string;
}

type IconMap = Record<string, React.ReactNode>;

export const Icon: React.FC<IconProps> = ({ name, size = 18, className = '' }) => {
  const s = { width: size, height: size };
  const stroke = {
    fill: 'none' as const,
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };

  const icons: IconMap = {
    barcode: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 5v14M7 5v14M11 5v14M15 5v14M19 5v14"/>
      </svg>
    ),
    search: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>
      </svg>
    ),
    plus: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M12 5v14M5 12h14"/>
      </svg>
    ),
    minus: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M5 12h14"/>
      </svg>
    ),
    trash: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>
      </svg>
    ),
    check: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="m5 12 5 5L20 7"/>
      </svg>
    ),
    x: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M6 6l12 12M18 6 6 18"/>
      </svg>
    ),
    card: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18"/>
      </svg>
    ),
    cash: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>
      </svg>
    ),
    wallet: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 7h15a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>
        <path d="M3 7V5a2 2 0 0 1 2-2h11"/>
        <circle cx="16.5" cy="13" r="1.2"/>
      </svg>
    ),
    receipt: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M5 3h14v18l-2-1.5L15 21l-2-1.5L11 21l-2-1.5L7 21 5 19.5V3Z"/>
        <path d="M8 8h8M8 12h8M8 16h5"/>
      </svg>
    ),
    printer: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M7 8V3h10v5M7 18H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
        <rect x="7" y="14" width="10" height="7" rx="1"/>
      </svg>
    ),
    mail: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <rect x="3" y="5" width="18" height="14" rx="2"/>
        <path d="m3 7 9 6 9-6"/>
      </svg>
    ),
    home: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="m3 11 9-8 9 8M5 9v11h14V9"/>
      </svg>
    ),
    pos: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <rect x="3" y="4" width="18" height="14" rx="2"/>
        <path d="M3 9h18M7 14h4"/>
      </svg>
    ),
    box: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="m3 7 9-4 9 4-9 4-9-4Z"/>
        <path d="M3 7v10l9 4 9-4V7M12 11v10"/>
      </svg>
    ),
    chart: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 3v18h18"/><path d="m7 15 4-5 4 3 5-7"/>
      </svg>
    ),
    users: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <circle cx="9" cy="8" r="3.5"/>
        <path d="M2 21c0-3.5 3-6 7-6s7 2.5 7 6M17 11a3 3 0 1 0 0-6M22 21c0-2.8-2-5-5-5.5"/>
      </svg>
    ),
    gear: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>
      </svg>
    ),
    logout: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>
      </svg>
    ),
    wifi: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/>
        <circle cx="12" cy="19" r="1" fill="currentColor"/>
      </svg>
    ),
    wifiOff: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 3l18 18M9 17a4 4 0 0 1 6 0M5 12.5a10 10 0 0 1 4-2.7M13 8.1a10 10 0 0 1 6 4.4"/>
        <circle cx="12" cy="19" r="1" fill="currentColor"/>
      </svg>
    ),
    sync: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8M21 4v4h-4M21 12a9 9 0 0 1-15.5 6.3L3 16M3 20v-4h4"/>
      </svg>
    ),
    bell: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M6 8a6 6 0 1 1 12 0c0 7 3 7 3 9H3c0-2 3-2 3-9ZM10 21a2 2 0 0 0 4 0"/>
      </svg>
    ),
    alert: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M12 3 2 21h20L12 3Z"/>
        <path d="M12 10v4M12 18h.01"/>
      </svg>
    ),
    filter: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 5h18l-7 9v6l-4-2v-4L3 5Z"/>
      </svg>
    ),
    chevR: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="m9 6 6 6-6 6"/>
      </svg>
    ),
    chevD: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="m6 9 6 6 6-6"/>
      </svg>
    ),
    arrowUp: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M12 19V5M5 12l7-7 7 7"/>
      </svg>
    ),
    arrowDn: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M12 5v14M5 12l7 7 7-7"/>
      </svg>
    ),
    eye: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/>
        <circle cx="12" cy="12" r="3"/>
      </svg>
    ),
    eyeOff: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="m3 3 18 18M9.9 5.1A11 11 0 0 1 12 5c6 0 10 7 10 7a18 18 0 0 1-3.4 4.2M6.6 6.6A18 18 0 0 0 2 12s4 7 10 7c1.3 0 2.5-.3 3.6-.7"/>
        <path d="M9.5 9.6a3 3 0 0 0 4.2 4.3"/>
      </svg>
    ),
    archive: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <rect x="3" y="3" width="18" height="5" rx="1"/>
        <path d="M5 8v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8"/>
        <path d="M10 12h4"/>
      </svg>
    ),
    truck: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 6h11v9H3zM14 9h4l3 3v3h-7z"/>
        <circle cx="8" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>
      </svg>
    ),
    bank: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 9l9-5 9 5M4 9v9M20 9v9M3 19h18M8 13v3M12 13v3M16 13v3"/>
      </svg>
    ),
    layers: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M12 3l9 5-9 5-9-5 9-5ZM3 13l9 5 9-5"/>
      </svg>
    ),
    tag: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M3 3h7l11 11-7 7L3 10V3Z"/>
        <path d="M7.5 7.5h.01"/>
      </svg>
    ),
    user: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <circle cx="12" cy="8" r="4"/>
        <path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>
      </svg>
    ),
    doc: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M6 2h8l4 4v16H6V2ZM14 2v4h4M9 13h6M9 17h6"/>
      </svg>
    ),
    shield: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M12 2l8 3v6c0 5-3.5 8-8 11-4.5-3-8-6-8-11V5l8-3Z"/>
      </svg>
    ),
    clock: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>
      </svg>
    ),
    chevL: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="m15 6-6 6 6 6"/>
      </svg>
    ),
    edit: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5Z"/>
      </svg>
    ),
    download: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M12 3v12M6 11l6 6 6-6M4 21h16"/>
      </svg>
    ),
    menu: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <path d="M4 6h16M4 12h16M4 18h16"/>
      </svg>
    ),
    lock: (
      <svg {...s} {...stroke} viewBox="0 0 24 24">
        <rect x="5" y="11" width="14" height="10" rx="2"/>
        <path d="M8 11V7a4 4 0 0 1 8 0v4"/>
      </svg>
    ),
  };

  const icon = icons[name];
  if (!icon) return null;
  return <span className={`inline-flex ${className}`}>{icon}</span>;
};
