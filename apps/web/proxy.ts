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
  matcher: ["/", "/login", "/consent", "/logout", "/error"],
}
