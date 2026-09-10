export async function preparationSubmissionMessage(
  response: Pick<Response, 'status' | 'json'>,
): Promise<string> {
  let code = '';
  try {
    const payload = (await response.json()) as { detail?: string | { code?: string } };
    code = typeof payload.detail === 'object' ? (payload.detail.code ?? '') : '';
  } catch {
    // Status-based fallbacks still give the operator an actionable result.
  }
  if (code === 'quota_exceeded')
    return 'Preparation was not submitted because the remaining lifetime allowance is too low.';
  if (code === 'invalid_csrf' || response.status === 401)
    return 'Your sign-in session could not authorize preparation. Sign out, sign in, and try again.';
  if (response.status === 502)
    return 'Preparation was recorded but Kestra could not be reached or authenticated. Ask an operator to check Kestra.';
  return `Preparation could not be submitted (HTTP ${response.status}).`;
}
