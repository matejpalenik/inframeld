import { Stopped } from "../../../components/account/stopped"

export const dynamic = "force-dynamic"

export default function ErrorPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold">Sign-in stopped</h1>
      <Stopped />
      <p>
        No access has been confirmed by this page. Check the requesting client
        for its final result.
      </p>
    </>
  )
}
