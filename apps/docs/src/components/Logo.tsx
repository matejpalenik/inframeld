export function Logo(props: React.ComponentPropsWithoutRef<"svg">) {
  return (
    <svg viewBox="0 0 156 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M2 3h8v8H2zM12 13h8v8h-8zM2 13h8v8H2z"
        className="fill-emerald-500"
      />
      <text
        x="29"
        y="18"
        fontSize="20"
        fontWeight="650"
        className="fill-zinc-900 dark:fill-white"
      >
        Inframeld
      </text>
    </svg>
  )
}
