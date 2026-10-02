import type { z } from "zod";
import { ApiClient } from "../lib/api/client";
import {
  accountsSchema,
  codeforcesAccountSchema,
  githubAccountSchema,
  leetcodeAccountSchema,
} from "../lib/api/schemas";
import { BACKEND_BASE_URL } from "../lib/config";
import { formatGrouped } from "../lib/format";

const client = new ApiClient(BACKEND_BASE_URL);

function setStat(key: string, value: number | null): void {
  if (value === null) {
    return;
  }
  for (const element of document.querySelectorAll<HTMLElement>(`[data-stat="${key}"]`)) {
    element.dataset.count = String(value);
    element.textContent = formatGrouped(value);
  }
}

async function load<T extends z.ZodType>(path: string, schema: T): Promise<z.infer<T> | null> {
  try {
    return await client.request(path, schema);
  } catch (error) {
    console.warn(`Live stats from ${path} unavailable; keeping the built snapshot`, error);
    return null;
  }
}

export async function startLiveStats(): Promise<void> {
  const [codeforces, leetcode, github] = await Promise.all([
    load("/details/codeforces", accountsSchema(codeforcesAccountSchema)),
    load("/details/leetcode", accountsSchema(leetcodeAccountSchema)),
    load("/details/github", accountsSchema(githubAccountSchema)),
  ]);

  for (const account of codeforces?.accounts ?? []) {
    setStat(`cf.${account.handle}.current`, account.current_rating);
    setStat(`cf.${account.handle}.max`, account.max_rating);
    setStat(`cf.${account.handle}.contests`, account.contests_count);
  }
  for (const account of leetcode?.accounts ?? []) {
    setStat(`lc.${account.username}.total`, account.total_solved);
    setStat(`lc.${account.username}.easy`, account.easy_solved);
    setStat(`lc.${account.username}.medium`, account.medium_solved);
    setStat(`lc.${account.username}.hard`, account.hard_solved);
  }
  for (const account of github?.accounts ?? []) {
    setStat(`gh.${account.username}.repos`, account.public_repos);
    setStat(`gh.${account.username}.followers`, account.followers);
  }
}
