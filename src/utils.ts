export function uid(prefix: string = "id"): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

export function now(): number {
  return Date.now();
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
