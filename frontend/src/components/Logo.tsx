"use client";

/**
 * The DRSCREEN mark: an aperture closing around an iris.
 *
 * Six blades on an outer ring (the instrument), a gradient iris (the eye),
 * a bright fovea core, and a sweep arc that rotates when `scanning` is set —
 * the same idea as a fundus camera stopping down before it captures.
 */
export function Logo({
  size = 40,
  scanning = false,
  className = "",
}: {
  size?: number;
  scanning?: boolean;
  className?: string;
}) {
  const id = `lg${size}${scanning ? "s" : ""}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={`${id}-iris`} x1="14" y1="12" x2="50" y2="52">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="55%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
        <radialGradient id={`${id}-core`} cx="42%" cy="38%" r="70%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="45%" stopColor="#a5f3fc" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${id}-sweep`} x1="32" y1="4" x2="32" y2="60">
          <stop offset="0%" stopColor="#67e8f9" />
          <stop offset="100%" stopColor="#67e8f9" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* aperture blades */}
      <g opacity="0.85">
        {[0, 60, 120, 180, 240, 300].map((deg) => (
          <path
            key={deg}
            d="M32 4.5 A27.5 27.5 0 0 1 55.8 18.25"
            stroke={`url(#${id}-iris)`}
            strokeWidth="3"
            strokeLinecap="round"
            transform={`rotate(${deg} 32 32)`}
          />
        ))}
      </g>

      <circle cx="32" cy="32" r="19.5" stroke={`url(#${id}-iris)`} strokeWidth="1.5" opacity="0.5" />
      <circle cx="32" cy="32" r="14" fill={`url(#${id}-iris)`} opacity="0.22" />
      <circle cx="32" cy="32" r="14" stroke={`url(#${id}-iris)`} strokeWidth="2" />
      <circle cx="32" cy="32" r="7.5" fill={`url(#${id}-core)`} />
      <circle cx="32" cy="32" r="2.6" fill="#ecfeff" />

      {scanning && (
        <g style={{ transformOrigin: "32px 32px", animation: "spin 2.4s linear infinite" }}>
          <path
            d="M32 6 A26 26 0 0 1 58 32"
            stroke={`url(#${id}-sweep)`}
            strokeWidth="2.5"
            strokeLinecap="round"
            fill="none"
          />
        </g>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`font-semibold tracking-[0.18em] ${className}`}>
      <span className="text-glow">DRSCREEN</span>
    </span>
  );
}
