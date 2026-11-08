import { NextResponse } from "next/server"
import { accountContentSecurityPolicy } from "./lib/account/security-headers"

export function proxy() {
  const response = NextResponse.next()
  response.headers.set(
    "Content-Security-Policy",
    accountContentSecurityPolicy(process.env)
  )
  return response
}

export const config = {
  matcher: [
    "/",
    "/login",
    "/registration",
    "/verification",
    "/recovery",
    "/settings",
    "/invitations",
    "/consent",
    "/logout",
    "/error",
  ],
}
