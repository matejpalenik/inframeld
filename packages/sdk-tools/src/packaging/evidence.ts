/** Runtime facts emitted only after an installed consumer completes its checks. */
export interface ConsumerEvidence {
  runtimes: {
    role: "primary" | "minimum";
    versions: Record<string, string>;
  }[];
}
