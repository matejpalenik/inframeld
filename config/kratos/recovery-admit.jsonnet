// Invoked only after native recovery-code verification.
function(ctx) {
  schemaVersion: 2,
  eventType: 'recovery-code-verified',
  identityId: ctx.identity.id,
  recoveryFlowId: ctx.flow.id,
  eventKind: 'recovery',
}
