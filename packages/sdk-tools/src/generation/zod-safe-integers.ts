import type { Plugins } from "@hey-api/openapi-ts";

/** Preserve JSON numbers when an int64 schema explicitly fits their exact range. */
export const jsonSafeInteger: NonNullable<Plugins.Zod.Resolvers["number"]> = (
  context,
) => {
  const { schema } = context;
  const minimum = schema.minimum;
  const maximum = schema.maximum;
  if (
    schema.type !== "integer" ||
    schema.format !== "int64" ||
    schema.const !== undefined ||
    schema.exclusiveMinimum !== undefined ||
    schema.exclusiveMaximum !== undefined ||
    typeof minimum !== "number" ||
    typeof maximum !== "number" ||
    !Number.isSafeInteger(minimum) ||
    !Number.isSafeInteger(maximum) ||
    minimum > maximum
  )
    return undefined;

  return context
    .$(context.symbols.z)
    .attr("int")
    .call()
    .attr("gte")
    .call(context.$.literal(minimum))
    .attr("lte")
    .call(context.$.literal(maximum));
};
