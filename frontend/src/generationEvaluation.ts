export const promptNames: Record<string, string> = {
  'basic-grounded-v1': 'Basic grounded v1',
  'structured-investor-v1': 'Structured investor v1',
  'basic-grounded-v2': 'Basic grounded v2',
  'structured-investor-v2': 'Structured investor v2',
  'guardrailed-10k-v3': 'Guardrailed 10-K v3',
};

export const verdictColor = (label: string | null) =>
  label === 'RELEVANT' ? 'success' : label === 'PARTLY_RELEVANT' ? 'warning' : 'error';
