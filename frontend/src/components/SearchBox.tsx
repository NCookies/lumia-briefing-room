interface Props {
  value: string
  onChange: (value: string) => void
  label: string
  placeholder: string
}

export function SearchBox({ value, onChange, label, placeholder }: Props) {
  return (
    <label className="relative block">
      <svg
        viewBox="0 0 24 24"
        className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="M20 20l-3.5-3.5" />
      </svg>
      <input
        type="search"
        aria-label={label}
        placeholder={placeholder}
        className="w-80 rounded-md border border-zinc-600/70 bg-zinc-900 py-1.5 pl-9 pr-3 text-sm outline-none focus:border-sky-500"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}
