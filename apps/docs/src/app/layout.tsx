import glob from "fast-glob"
import { type Metadata } from "next"

import { pageMetadata as introductionMetadata } from "./page.mdx"

import { Providers } from "@/app/providers"
import { Layout } from "@/components/Layout"
import { type Section } from "@/components/SectionProvider"

import "@/styles/tailwind.css"

export const metadata: Metadata = {
  ...introductionMetadata,
  title: {
    template: "%s - Inframeld documentation",
    default: introductionMetadata.title,
  },
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pages = await glob("**/*.mdx", { cwd: "src/app" })
  const allSectionsEntries = (await Promise.all(
    pages.map(async (filename) => [
      ("/" + filename.replace(/(^|\/)page\.mdx$/, "")).replace(/\/$/, "") ||
        "/",
      (await import(`./${filename}`)).sections,
    ])
  )) as Array<[string, Array<Section>]>
  const allSections = Object.fromEntries(allSectionsEntries)

  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="flex min-h-full bg-white antialiased dark:bg-zinc-900">
        <Providers>
          <div className="w-full">
            <Layout allSections={allSections}>{children}</Layout>
          </div>
        </Providers>
      </body>
    </html>
  )
}
