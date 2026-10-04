export function withKeys<T>(items: readonly T[], label: (item: T) => string): readonly (readonly [string, T])[] {
  const seen = new Map<string, number>();
  return items.map((item) => {
    const base = label(item);
    const occurrence = (seen.get(base) ?? 0) + 1;
    seen.set(base, occurrence);
    return [`${base}#${occurrence}`, item] as const;
  });
}

export function describe(value: unknown): string {
  return JSON.stringify(value).slice(0, 120);
}
