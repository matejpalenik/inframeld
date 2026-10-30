"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { Button } from "@/components/Button"
import { navigation } from "@/components/Navigation"

function PageLink({
  label,
  page,
  previous = false,
}: {
  label: string
  page: { href: string; title: string }
  previous?: boolean
}) {
  return (
    <>
      <Button
        href={page.href}
        aria-label={`${label}: ${page.title}`}
        variant="secondary"
        arrow={previous ? "left" : "right"}
      >
        {label}
      </Button>
      <Link
        href={page.href}
        tabIndex={-1}
        aria-hidden="true"
        className="text-base font-semibold text-zinc-900 transition hover:text-zinc-600 dark:text-white dark:hover:text-zinc-300"
      >
        {page.title}
      </Link>
    </>
  )
}

function PageNavigation() {
  const pathname = usePathname()
  const allPages = navigation.flatMap((group) => group.links)
  const currentPageIndex = allPages.findIndex((page) => page.href === pathname)

  if (currentPageIndex === -1) {
    return null
  }

  const previousPage = allPages[currentPageIndex - 1]
  const nextPage = allPages[currentPageIndex + 1]

  if (!previousPage && !nextPage) {
    return null
  }

  return (
    <div className="flex">
      {previousPage && (
        <div className="flex flex-col items-start gap-3">
          <PageLink label="Previous" page={previousPage} previous />
        </div>
      )}
      {nextPage && (
        <div className="ml-auto flex flex-col items-end gap-3">
          <PageLink label="Next" page={nextPage} />
        </div>
      )}
    </div>
  )
}

function SmallPrint() {
  return (
    <div className="flex flex-col gap-5 border-t border-zinc-900/5 pt-8 text-xs text-zinc-600 sm:flex-row sm:justify-between dark:border-white/5 dark:text-zinc-400">
      <p>Inframeld documentation</p>
      <div className="flex gap-4">
        <Link href="https://github.com/matejpalenik/inframeld">
          Source on GitHub
        </Link>
        <Link href="https://github.com/matejpalenik/inframeld/issues">
          Report a documentation issue
        </Link>
      </div>
    </div>
  )
}

export function Footer() {
  return (
    <footer className="mx-auto w-full max-w-2xl space-y-10 pb-16 lg:max-w-5xl">
      <PageNavigation />
      <SmallPrint />
    </footer>
  )
}
