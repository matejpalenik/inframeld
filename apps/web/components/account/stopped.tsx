import Link from "next/link"

export function Stopped({
  message = "This sign-in request could not continue. Return to the requesting client and start again.",
}: {
  message?: string
}) {
  return (
    <>
      <p role="alert">{message}</p>
      <p>
        <Link href="/" className="underline underline-offset-4">
          Return to account home
        </Link>
      </p>
    </>
  )
}
