import Link from "next/link"

export default function AccountLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-svh bg-background px-5 py-10 text-foreground sm:py-16">
      <header className="mx-auto mb-10 max-w-lg">
        <Link href="/" className="font-semibold tracking-tight">
          Inframeld account
        </Link>
      </header>
      <main className="mx-auto max-w-lg space-y-6">{children}</main>
    </div>
  )
}
