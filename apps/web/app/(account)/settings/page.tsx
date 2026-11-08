import { NativeFlowPage } from "../../../components/account/native-flow-page"

export const dynamic = "force-dynamic"

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  return <NativeFlowPage kind="settings" searchParams={searchParams} />
}
