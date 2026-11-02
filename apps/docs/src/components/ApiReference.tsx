import contract from "../../../../contracts/openapi/v1/inframeld-v1.json"

interface Schema {
  [key: string]: unknown
  $ref?: string
  type?: string
  properties?: Record<string, Schema>
  required?: string[]
  description?: string
  items?: Schema
  anyOf?: Schema[]
  oneOf?: Schema[]
}

interface Representation {
  schema?: Schema
}

interface Operation {
  operationId: string
  parameters?: Array<{
    name: string
    in: string
    required?: boolean
    description?: string
    schema?: Schema
  }>
  requestBody?: { required?: boolean; content: Record<string, Representation> }
  responses: Record<
    string,
    { description: string; content?: Record<string, Representation> }
  >
}

const document: {
  paths: Record<string, Record<string, Operation>>
  components: { schemas: Record<string, Schema> }
} = contract

function schemaType(schema: Schema): string {
  if (schema.$ref) return schema.$ref.split("/").at(-1) ?? "object"
  const variants = schema.oneOf ?? schema.anyOf
  if (variants) return variants.map(schemaType).join(" | ")
  if (schema.type === "array")
    return `array of ${schemaType(schema.items ?? {})}`
  if (schema.const !== undefined) return JSON.stringify(schema.const)
  if (Array.isArray(schema.enum))
    return schema.enum.map((value) => JSON.stringify(value)).join(" | ")
  return schema.type ?? "object"
}

function SchemaLink({ schema }: { schema?: Schema }) {
  if (!schema) return <>No response body</>
  const name = schema.$ref?.split("/").at(-1)
  return name ? (
    <a href={`/api-reference/models#${name}`}>{name}</a>
  ) : (
    <code>{schemaType(schema)}</code>
  )
}

/** Display a delivered operation directly from the committed public contract. */
export function ApiOperation({ operationId }: { operationId: string }) {
  for (const [path, methods] of Object.entries(document.paths)) {
    for (const [method, operation] of Object.entries(methods)) {
      if (operation.operationId !== operationId) continue
      return (
        <div className="overflow-x-auto">
          <p>
            <code>
              {method.toUpperCase()} {path}
            </code>
          </p>
          <p>
            Operation ID: <code>{operationId}</code>.
          </p>
          {operation.parameters && operation.parameters.length > 0 && (
            <>
              <h3>Parameters</h3>
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Location</th>
                    <th>Required</th>
                    <th>Type</th>
                  </tr>
                </thead>
                <tbody>
                  {operation.parameters.map((parameter) => (
                    <tr key={`${parameter.in}:${parameter.name}`}>
                      <td>
                        <code>{parameter.name}</code>
                        {parameter.description && (
                          <p>{parameter.description}</p>
                        )}
                      </td>
                      <td>{parameter.in}</td>
                      <td>{parameter.required ? "Yes" : "No"}</td>
                      <td>
                        <SchemaLink schema={parameter.schema} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {operation.requestBody && (
            <>
              <h3>Request body</h3>
              <p>
                {operation.requestBody.required ? "Required." : "Optional."}
              </p>
              <ul>
                {Object.entries(operation.requestBody.content).map(
                  ([media, value]) => (
                    <li key={media}>
                      <code>{media}</code>: <SchemaLink schema={value.schema} />
                    </li>
                  )
                )}
              </ul>
            </>
          )}
          <h3>Responses</h3>
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Description</th>
                <th>Body</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(operation.responses).map(([status, response]) => (
                <tr key={status}>
                  <td>
                    <code>{status}</code>
                  </td>
                  <td>{response.description}</td>
                  <td>
                    {response.content
                      ? Object.entries(response.content).map(
                          ([media, value]) => (
                            <p key={media}>
                              <code>{media}</code>:{" "}
                              <SchemaLink schema={value.schema} />
                            </p>
                          )
                        )
                      : "No body"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <details>
            <summary>Complete OpenAPI operation</summary>
            <pre>
              <code>{JSON.stringify(operation, null, 2)}</code>
            </pre>
          </details>
        </div>
      )
    }
  }
  throw new Error(`Unknown public operation: ${operationId}`)
}

/** Display fields and the complete native schema without a second handwritten model. */
export function ApiSchema({ name }: { name: string }) {
  const schema = document.components.schemas[name]
  if (!schema) throw new Error(`Unknown public schema: ${name}`)
  return (
    <div className="overflow-x-auto">
      {schema.description && <p>{schema.description}</p>}
      {schema.properties && (
        <table>
          <thead>
            <tr>
              <th>Field</th>
              <th>Required</th>
              <th>Type</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(schema.properties).map(([field, value]) => (
              <tr key={field}>
                <td>
                  <code>{field}</code>
                </td>
                <td>{schema.required?.includes(field) ? "Yes" : "No"}</td>
                <td>
                  <SchemaLink schema={value} />
                </td>
                <td>{value.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <details>
        <summary>Complete JSON Schema</summary>
        <pre>
          <code>{JSON.stringify(schema, null, 2)}</code>
        </pre>
      </details>
    </div>
  )
}
