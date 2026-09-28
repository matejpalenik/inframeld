local claims = std.extVar('claims');

if !std.objectHas(claims, 'email') ||
   !std.objectHas(claims, 'email_verified') ||
   claims.email_verified != true
then error 'OIDC provider must return a verified email'
else {
  identity: {
    traits: {
      email: claims.email,
    },
  },
}