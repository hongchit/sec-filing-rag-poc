export function safeLocalReturnTo(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\'))
    return '/research';
  try {
    const target = new URL(value, window.location.origin);
    return target.origin === window.location.origin
      ? `${target.pathname}${target.search}${target.hash}`
      : '/research';
  } catch {
    return '/research';
  }
}

export function signInPath(returnTo: string): string {
  return `/sign-in?return_to=${encodeURIComponent(safeLocalReturnTo(returnTo))}`;
}
