interface Props {
  value: string
  onChange: (value: string) => void
  label: string
  placeholder: string
}

export function SearchBox({ value, onChange, label, placeholder }: Props) {
  return (
    <input
      type="search"
      aria-label={label}
      placeholder={placeholder}
      className="w-80 rounded-md border border-zinc-600/70 bg-zinc-900 px-3 py-1.5 text-sm outline-none focus:border-sky-500"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}
