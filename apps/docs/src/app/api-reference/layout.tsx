import type { ReactNode } from "react"

export { pageMetadata as metadata } from "./page.mdx"

export default function Layout({ children }: { children: ReactNode }) {
  return children
}
