// Next 16's MDX Webpack loader uses a general compiler pass that rejects the
// reserved metadata export. A server layout exposes the MDX-authored metadata.
export { pageMetadata as metadata } from "./page.mdx"

export default function GuideLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
