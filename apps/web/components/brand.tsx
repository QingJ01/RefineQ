interface BrandMarkProps {
  className?: string;
  decorative?: boolean;
  size?: number;
  title?: string;
}


export function BrandMark({
  className,
  decorative = true,
  size = 34,
  title = "RefineQ",
}: BrandMarkProps) {
  return (
    <svg
      className={className}
      data-brand-mark="refineq-q-page"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": title })}
    >
      <rect x="2" y="2" width="60" height="60" rx="16" fill="#2A63E8" />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M32 11C19.85 11 10 20.85 10 33C10 45.15 19.85 55 32 55C44.15 55 54 45.15 54 33C54 20.85 44.15 11 32 11ZM32 22.5C26.2 22.5 21.5 27.2 21.5 33C21.5 38.8 26.2 43.5 32 43.5C37.8 43.5 42.5 38.8 42.5 33C42.5 27.2 37.8 22.5 32 22.5Z"
        fill="#FFFDF8"
      />
      <path d="M40 42H53.5V58L40 48.5V42Z" fill="#FFFDF8" />
      <path data-brand-fold="true" d="M40 42H53.5V52.25L40 42Z" fill="#CFDBFF" />
      <circle data-brand-progress="true" cx="13.5" cy="49.5" r="4.5" fill="#FFAD73" />
    </svg>
  );
}

export function BrandName({ className }: { className?: string }) {
  return (
    <strong
      className={className ? `brand-name ${className}` : "brand-name"}
      data-brand-name="RefineQ"
      translate="no"
    >
      Refine<span>Q</span>
    </strong>
  );
}
