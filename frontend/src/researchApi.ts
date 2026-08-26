import type { Research } from './researchTypes';

export async function streamResearch(
  body: object,
  key: string,
  onEvent: (name: string, data: unknown) => void,
): Promise<Research> {
  const response = await fetch('/api/research/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body)
    throw new Error(`Research stream unavailable (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      const event = block.match(/^event: (.+)$/m)?.[1];
      const raw = block.match(/^data: (.+)$/m)?.[1];
      if (!event || !raw) continue;
      const data: unknown = JSON.parse(raw);
      onEvent(event, data);
      if (event === 'succeeded') return data as Research;
      if (event === 'failed') throw Object.assign(new Error('Research failed'), { detail: data });
    }
    if (done) throw new Error('Research stream ended before completion');
  }
}

export async function recoverResearch(
  body: object,
  key: string,
  researchId?: string,
): Promise<Research> {
  if (researchId) {
    const found = await fetch(`/api/research/${researchId}`);
    if (found.ok) return found.json() as Promise<Research>;
  }
  const response = await fetch('/api/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
    body: JSON.stringify(body),
  });
  const payload = (await response.json()) as Research | { detail?: { research_id?: string } };
  if (response.status === 409 && 'detail' in payload && payload.detail?.research_id)
    return recoverResearch(body, key, payload.detail.research_id);
  if (!response.ok) throw new Error(`Research failed (${response.status})`);
  return payload as Research;
}
