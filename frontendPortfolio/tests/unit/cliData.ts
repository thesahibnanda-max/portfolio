import { readFile } from "node:fs/promises";
import {
  accountsSchema,
  cliManifestSchema,
  codeforcesAccountSchema,
  githubAccountSchema,
  leetcodeAccountSchema,
  professionalSchema,
  profileSchema,
} from "../../src/lib/api/schemas";
import { buildRegistry, type CommandContext } from "../../src/lib/cli/commands";
import type { CliData } from "../../src/lib/cli/data";
import { type CliSettings, defaultSettings } from "../../src/lib/cli/settings";

async function fixture(name: string): Promise<unknown> {
  return JSON.parse(await readFile(new URL(`../fixtures/api/${name}.json`, import.meta.url), "utf8"));
}

const profile = profileSchema.parse(await fixture("profile"));

export const DATA: CliData = {
  ownerName: profile.profile_details.name,
  profile,
  professional: professionalSchema.parse(await fixture("professional")),
  leetcode: accountsSchema(leetcodeAccountSchema).parse(await fixture("leetcode")).accounts,
  codeforces: accountsSchema(codeforcesAccountSchema).parse(await fixture("codeforces")).accounts,
  github: accountsSchema(githubAccountSchema).parse(await fixture("github")).accounts,
  resumeUrl: "http://api.test/details/resume?v=0123456789abcdef",
  builtAt: "2026-10-04T00:00:00.000Z",
  manifest: cliManifestSchema.parse(await fixture("cli")),
};

export const SETTINGS = defaultSettings(DATA.manifest);

export function contextFor(settings: CliSettings = SETTINGS): CommandContext {
  return {
    data: DATA,
    now: new Date("2026-10-04T00:00:00Z"),
    settings,
    registry: buildRegistry(DATA.manifest, settings),
    random: () => 0,
  };
}

export const CONTEXT = contextFor();
