"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

export type UrlFilterState = Record<string, string>;
export type UrlFilterUpdate = Record<string, string | undefined | null>;

export function useUrlFilters(keys: readonly string[], defaults: Readonly<Record<string, string>> = {}) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();

  const value: UrlFilterState = { ...defaults };
  for (const key of keys) {
    const current = search.get(key);
    if (current !== null && current !== "") value[key] = current;
    else if (!(key in defaults)) delete value[key];
  }

  const setValue = (next: UrlFilterUpdate) => {
    const params = new URLSearchParams();
    for (const key of keys) {
      const current = next[key];
      if (current !== undefined && current !== null && current !== "") params.set(key, String(current));
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  return [value, setValue] as const;
}
