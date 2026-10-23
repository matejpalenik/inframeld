// Test observation only. Never copy credentials or the complete hook context.
function(ctx)
  local source = std.split(ctx.flow.request_url, '?');
  local parameters = if std.length(source) == 2 then std.split(source[1], '&') else [];
  local pairs = [std.split(parameter, '=') for parameter in parameters];
  local flowIds = [pair[1] for pair in pairs if std.length(pair) == 2 && pair[0] == 'flow'];
  {
    settingsFlowId: ctx.flow.id,
    identityId: ctx.identity.id,
    sessionId: if std.objectHas(ctx, 'session') then ctx.session.id else null,
    sourceRecoveryFlowId:
      if source[0] == 'http://kratos:4433/self-service/recovery' && std.length(flowIds) == 1
      then flowIds[0] else null,
    phase: 'before',
  }
