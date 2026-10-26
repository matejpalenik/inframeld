// Keep these source guards mirrored in both templates. Kratos forbids Jsonnet imports.
// Derive the recovery endpoint from the provider-generated settings action.
function(ctx)
  local action = std.split(ctx.flow.ui.action, '/self-service/settings');
  local source = std.splitLimit(ctx.flow.request_url, '?', 1);
  local is_recovery = std.length(action) == 2 && source[0] == action[0] + '/self-service/recovery';
  local params = if std.length(source) == 2 then std.split(source[1], '&') else [];
  local pairs = [std.splitLimit(param, '=', 1) for param in params];
  local flows = [pair[1] for pair in pairs if std.length(pair) == 2 && pair[0] == 'flow'];

  local has_only(value, characters) =
    std.length([char for char in std.stringChars(value) if !std.member(characters, char)]) == 0;
  local plain_name_characters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~';
  local valid_fields = std.length(source) == 2 && std.length([
    pair for pair in pairs
    if std.length(pair) != 2 || std.length(pair[0]) == 0 || !has_only(pair[0], plain_name_characters)
  ]) == 0;
  local is_uuid(value) =
    local groups = std.split(value, '-');
    [std.length(group) for group in groups] == [8, 4, 4, 4, 12] &&
    has_only(std.join('', groups), '0123456789abcdefABCDEF');

  local recovery_source =
    if !is_recovery then null
    else if valid_fields && std.length(flows) == 1 && is_uuid(flows[0]) then flows[0]
    else error 'Invalid native recovery source.';

  {
    schemaVersion: 2,
    eventType: 'settings-flow-associated',
    identityId: ctx.session.identity.id,
    settingsFlowId: ctx.flow.id,
    sessionId: ctx.session.id,
    sourceRecoveryFlowId: recovery_source,
  }
