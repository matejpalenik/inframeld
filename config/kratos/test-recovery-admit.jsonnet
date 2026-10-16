function(ctx) {
  schemaVersion: 1,
  flowId: ctx.flow.id,
  identityId: ctx.identity.id,
  eventKind: 'recovery',
  phase: 'admit',
}