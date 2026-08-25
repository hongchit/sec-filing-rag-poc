export async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(
      response.status === 409
        ? 'Evaluation integrity check failed'
        : `Could not load evaluation (${response.status})`,
    );
  const payload: unknown = await response.json();
  return payload as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected error';
}
