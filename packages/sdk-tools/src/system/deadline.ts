/** Bound library promises whose cleanup APIs do not accept AbortSignal. */
export async function withinDeadline<T>(
  task: Promise<T>,
  milliseconds: number,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const expired = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () =>
        reject(new Error(`Operation exceeded its ${milliseconds}ms deadline`)),
      milliseconds,
    );
  });
  try {
    return await Promise.race([task, expired]);
  } finally {
    clearTimeout(timer);
  }
}
