import React from "react";

const base = (props) => ({
  width: props.size || 20,
  height: props.size || 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
});

export const SearchIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="11" cy="11" r="7" />
    <line x1="21" y1="21" x2="16.5" y2="16.5" />
  </svg>
);

export const HomeIcon = (p) => (
  <svg {...base(p)}>
    <path d="M3 10.5 12 3l9 7.5" />
    <path d="M5 9.5V21h14V9.5" />
    <path d="M10 21v-6h4v6" />
  </svg>
);

export const PlayCircleIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <polygon points="10,8.5 16,12 10,15.5" fill="currentColor" stroke="none" />
  </svg>
);

export const PlayIcon = (p) => (
  <svg {...base(p)}>
    <polygon points="7,4.5 19,12 7,19.5" fill="currentColor" stroke="none" />
  </svg>
);

export const PauseIcon = (p) => (
  <svg {...base(p)}>
    <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none" />
    <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none" />
  </svg>
);

export const InsightsIcon = (p) => (
  <svg {...base(p)}>
    <line x1="4" y1="20" x2="20" y2="20" />
    <rect x="5" y="12" width="3.5" height="8" rx="1" />
    <rect x="10.5" y="7" width="3.5" height="13" rx="1" />
    <rect x="16" y="3" width="3.5" height="17" rx="1" />
  </svg>
);

export const CoachingIcon = (p) => (
  <svg {...base(p)}>
    <path d="M22 9 12 4 2 9l10 5 10-5z" />
    <path d="M6 11.5V16c0 1.5 2.7 3 6 3s6-1.5 6-3v-4.5" />
  </svg>
);

export const ReportsIcon = (p) => (
  <svg {...base(p)}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="13" y2="17" />
  </svg>
);

export const SettingsIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09c0-.69-.41-1.3-1.04-1.56a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1.03H3a2 2 0 1 1 0-4h.09c.69 0 1.3-.41 1.56-1.04A1.7 1.7 0 0 0 4.3 7.06l-.06-.06A2 2 0 1 1 7.08 4.17l.06.06c.5.49 1.23.62 1.86.34A1.7 1.7 0 0 0 10.04 3V3a2 2 0 1 1 4 0v.09c0 .68.41 1.3 1.03 1.56.64.27 1.37.14 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.86c.26.63.88 1.04 1.56 1.04H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1.03z" />
  </svg>
);

export const HeartIcon = (p) => (
  <svg {...base(p)} fill={p.filled ? "currentColor" : "none"}>
    <path d="M20.4 4.6a5.5 5.5 0 0 0-7.8 0L12 5.2l-.6-.6a5.5 5.5 0 1 0-7.8 7.8l.6.6L12 20.8 19.8 13l.6-.6a5.5 5.5 0 0 0 0-7.8z" />
  </svg>
);

export const ShareIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="18" cy="5" r="3" />
    <circle cx="6" cy="12" r="3" />
    <circle cx="18" cy="19" r="3" />
    <line x1="8.6" y1="10.5" x2="15.4" y2="6.5" />
    <line x1="8.6" y1="13.5" x2="15.4" y2="17.5" />
  </svg>
);

export const CommentIcon = (p) => (
  <svg {...base(p)}>
    <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.6 8.6 0 0 1-3.8-.9L3 20l1-4.9A8.4 8.4 0 1 1 21 11.5z" />
  </svg>
);

export const HeadphonesIcon = (p) => (
  <svg {...base(p)}>
    <path d="M4 14v-3a8 8 0 0 1 16 0v3" />
    <rect x="3" y="14" width="4" height="6" rx="2" />
    <rect x="17" y="14" width="4" height="6" rx="2" />
  </svg>
);

export const ChevronLeftIcon = (p) => (
  <svg {...base(p)}>
    <polyline points="14.5,5 8,12 14.5,19" />
  </svg>
);

export const ChevronRightIcon = (p) => (
  <svg {...base(p)}>
    <polyline points="9.5,5 16,12 9.5,19" />
  </svg>
);

export const PlusIcon = (p) => (
  <svg {...base(p)}>
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);

export const XIcon = (p) => (
  <svg {...base(p)}>
    <line x1="6" y1="6" x2="18" y2="18" />
    <line x1="18" y1="6" x2="6" y2="18" />
  </svg>
);

export const CheckIcon = (p) => (
  <svg {...base(p)}>
    <polyline points="4.5,12.5 10,18 19.5,6.5" />
  </svg>
);

export const CheckCircleIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <polyline points="8,12.5 11,15.5 16.5,9" />
  </svg>
);

export const TrashIcon = (p) => (
  <svg {...base(p)}>
    <polyline points="3,6 5,6 21,6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </svg>
);

export const EditIcon = (p) => (
  <svg {...base(p)}>
    <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z" />
  </svg>
);

export const PhoneIcon = (p) => (
  <svg {...base(p)}>
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.13.96.36 1.9.7 2.8a2 2 0 0 1-.45 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.45c.9.34 1.84.57 2.8.7A2 2 0 0 1 22 16.9z" />
  </svg>
);

export const VideoIcon = (p) => (
  <svg {...base(p)}>
    <path d="M16 10.5l5-3.5v10l-5-3.5" />
    <rect x="2" y="6" width="14" height="12" rx="2" />
  </svg>
);

export const LogoutIcon = (p) => (
  <svg {...base(p)}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16,17 21,12 16,7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

export const ClockIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <polyline points="12,7 12,12 15.5,14" />
  </svg>
);

export const BookmarkIcon = (p) => (
  <svg {...base(p)} fill={p.filled ? "currentColor" : "none"}>
    <path d="M19 21 12 16.5 5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </svg>
);

export const ArrowUpIcon = (p) => (
  <svg {...base(p)}>
    <line x1="12" y1="19" x2="12" y2="5" />
    <polyline points="5,12 12,5 19,12" />
  </svg>
);

export const FlameIcon = (p) => (
  <svg {...base(p)}>
    <path d="M12 22c4.4 0 7-2.8 7-7 0-3-1.5-5.2-3-7-.5 1.5-1.4 2.3-2.5 2.5C13.8 8 14 5 11 2c.5 4-4 5.5-5.5 9-.4 1-.5 2-.5 3 0 4.2 2.6 8 7 8z" />
  </svg>
);

export const PlaylistIcon = (p) => (
  <svg {...base(p)}>
    <line x1="3" y1="6" x2="13" y2="6" />
    <line x1="3" y1="11" x2="13" y2="11" />
    <line x1="3" y1="16" x2="9" y2="16" />
    <polygon points="14,13 21,16.5 14,20" fill="currentColor" stroke="none" />
  </svg>
);

export const MicIcon = (p) => (
  <svg {...base(p)}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
    <line x1="12" y1="18" x2="12" y2="22" />
    <line x1="8.5" y1="22" x2="15.5" y2="22" />
  </svg>
);

export const BuildingIcon = (p) => (
  <svg {...base(p)}>
    <rect x="4" y="3" width="16" height="18" rx="1.5" />
    <line x1="9" y1="7" x2="9" y2="7.01" />
    <line x1="15" y1="7" x2="15" y2="7.01" />
    <line x1="9" y1="11" x2="9" y2="11.01" />
    <line x1="15" y1="11" x2="15" y2="11.01" />
    <path d="M10 21v-4h4v4" />
  </svg>
);

export const TrendingUpIcon = (p) => (
  <svg {...base(p)}>
    <polyline points="3,16 9,10 13,14 21,6" />
    <polyline points="15,6 21,6 21,12" />
  </svg>
);

export const TrophyIcon = (p) => (
  <svg {...base(p)}>
    <path d="M7 4h10v5a5 5 0 0 1-10 0V4z" />
    <path d="M7 6H4v1a3 3 0 0 0 3 3" />
    <path d="M17 6h3v1a3 3 0 0 1-3 3" />
    <line x1="12" y1="14" x2="12" y2="18" />
    <path d="M8.5 21h7l-.7-3h-5.6z" />
  </svg>
);

export const UsersIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
    <path d="M16 5.2a3.2 3.2 0 0 1 0 6" />
    <path d="M17.5 14.4A5.5 5.5 0 0 1 21 19.5" />
  </svg>
);

export const MailIcon = (p) => (
  <svg {...base(p)}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" />
  </svg>
);

export const GlobeIcon = (p) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18" />
  </svg>
);

export const LinkedinIcon = (p) => (
  <svg {...base(p)}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <line x1="7.5" y1="10" x2="7.5" y2="16.5" />
    <line x1="7.5" y1="7" x2="7.5" y2="7.01" />
    <path d="M11 16.5V10m0 2.5a3 3 0 0 1 6 0v4" />
  </svg>
);

export const MapPinIcon = (p) => (
  <svg {...base(p)}>
    <path d="M12 21s-6-5.3-6-10a6 6 0 0 1 12 0c0 4.7-6 10-6 10z" />
    <circle cx="12" cy="11" r="2.2" />
  </svg>
);
