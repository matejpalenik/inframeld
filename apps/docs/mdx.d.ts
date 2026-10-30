declare module "*.mdx" {
  export const pageMetadata: import("next").Metadata & {
    title: string
    description: string
  }
  export const sections: Array<import("@/components/SectionProvider").Section>
  const MDXContent: import("mdx/types").MDXContent
  export default MDXContent
}
