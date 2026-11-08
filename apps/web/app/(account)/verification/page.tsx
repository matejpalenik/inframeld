import { NativeFlowPage } from "../../../components/account/native-flow-page"

export const dynamic = "force-dynamic"

export default async function VerificationPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  return <NativeFlowPage kind="verification" searchParams={searchParams} />
}
