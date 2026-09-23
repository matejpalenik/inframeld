# Cursor pagination

List endpoints use `limit` and an optional opaque `cursor`. They return `items` and `nextCursor`. A null `nextCursor` means there is no next page.

The shared HTTP models are `PaginationQuery` and `PageResponse[Item]` in `apps/backend/src/inframeld_backend/shared/http/pagination.py`. `limit` defaults to 25 and must be between 1 and 100, inclusive. Cursor text must be nonempty, at most 1024 characters, and use the unpadded URL-safe base64 character set. Invalid query values receive the existing RFC 9457 validation response.

## Rules for an owning list endpoint

1. Authenticate and authorize **every** page request. A cursor identifies a position; possessing one does not grant access.
2. Apply the caller's scope and filters on every request, including requests with a cursor.
3. Choose a deterministic order ending in a unique tie-breaker. For example, order by `created_at DESC, id DESC`, then resume after both values.
4. Decode and validate the cursor's contents for this endpoint and its current sort, filters, and scope. Reject malformed or incompatible contents with a safe 422 problem. Passing the shared character check alone does not make a cursor valid.
5. Fetch at most `limit + 1` matching records to determine whether another page exists. Return no more than `limit` items; issue `nextCursor` only when another page exists.
6. Never place credentials, private content, or other sensitive values in a cursor. Encoding is not encryption. Do not log the raw cursor.

Declare `PageResponse[Item]` as the success response and the applicable problem responses in OpenAPI. Cursor contents and database queries belong to the feature that owns the list; this shared contract does not prescribe either.

Example: if two records have the same `created_at`, the unique `id` decides their order. A cursor containing only the timestamp could skip one of them.
