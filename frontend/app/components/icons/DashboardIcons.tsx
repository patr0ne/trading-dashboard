import type { ReactNode } from "react";

export type IconProps = {
  className?: string;
  title?: string;
};

type IconFrameProps = IconProps & {
  children: ReactNode;
};

function IconFrame({ className, title, children }: IconFrameProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {children}
    </svg>
  );
}

export function DashboardLogoIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="M5.5 4.5h13a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2Z" />
      <path d="M6.8 15.2h2.6l1.9-4.2 2.3 6 2.1-4 1.7 2.2h1.8" />
    </IconFrame>
  );
}

export function PulseIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="M3 12h4l2.2-4.5 3.4 9.5 2.3-5H21" />
    </IconFrame>
  );
}

export function TickerStackIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="m12 4 8 4.5-8 4.5-8-4.5L12 4Z" />
      <path d="m20 12-8 4.5L4 12" />
      <path d="m20 16-8 4.5L4 16" />
    </IconFrame>
  );
}

export function TradeFlowIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="M4 16 9 11l3.3 3.3L20 6.6" />
      <path d="M15.8 6.6H20v4.2" />
    </IconFrame>
  );
}

export function CandlesIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="M7 4v16" />
      <path d="M5.6 8.3h2.8v5.6H5.6Z" />
      <path d="M14.5 3v18" />
      <path d="M13.1 7.2h2.8v8.2h-2.8Z" />
      <path d="M19 6.5v11" />
      <path d="M17.6 10h2.8v4.5h-2.8Z" />
    </IconFrame>
  );
}

export function OrderbookDepthIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="M4 6h10" />
      <path d="M4 12h14" />
      <path d="M4 18h8" />
      <path d="M17 5v14" />
    </IconFrame>
  );
}

export function SunIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.8v2.4" />
      <path d="M12 18.8v2.4" />
      <path d="M2.8 12h2.4" />
      <path d="M18.8 12h2.4" />
      <path d="m5.5 5.5 1.7 1.7" />
      <path d="m16.8 16.8 1.7 1.7" />
      <path d="m18.5 5.5-1.7 1.7" />
      <path d="m7.2 16.8-1.7 1.7" />
    </IconFrame>
  );
}

export function MoonIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="M19.4 14.7A8.2 8.2 0 1 1 9.3 4.6a6.8 6.8 0 1 0 10.1 10.1Z" />
    </IconFrame>
  );
}

export function TimeframeIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 7.8v4.6l3.2 1.8" />
    </IconFrame>
  );
}

export function PairIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="M9.1 7.2H7.2a3.2 3.2 0 0 0 0 6.4h1.9" />
      <path d="M14.9 16.8h1.9a3.2 3.2 0 1 0 0-6.4h-1.9" />
      <path d="M8.8 12h6.4" />
    </IconFrame>
  );
}

export function ScaleIcon({ className, title }: IconProps) {
  return (
    <IconFrame className={className} title={title}>
      <path d="M5 18.5V5.5" />
      <path d="M5 18.5h14" />
      <path d="m8.2 14.8 3.2-3.2 2.3 2.3 4.3-4.3" />
    </IconFrame>
  );
}
