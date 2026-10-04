import type { CliArgSource, CliManifest } from "../api/schemas";
import {
  codeforcesRank,
  experienceDuration,
  formatGrouped,
  formatYearMonth,
  isCurrent,
  profileHandle,
} from "../format";
import { type Block, error, hint, type Line, link, span } from "./blocks";
import type { CliData, LiveStats } from "./data";
import { findByName } from "./parser";
import { type CliSettings, changePlugin, changeSetting, isPluginEnabled, settingValue } from "./settings";

export type StatsTarget = "all" | "leetcode" | "codeforces" | "github";

export type CommandEffect =
  | { readonly kind: "print"; readonly blocks: readonly Block[] }
  | { readonly kind: "clear" }
  | { readonly kind: "navigate"; readonly href: string; readonly blocks: readonly Block[] }
  | { readonly kind: "open-url"; readonly url: string; readonly blocks: readonly Block[] }
  | { readonly kind: "ask"; readonly question: string }
  | { readonly kind: "new-chat" }
  | { readonly kind: "list-chats" }
  | { readonly kind: "open-chat"; readonly index: number }
  | { readonly kind: "stats"; readonly target: StatsTarget }
  | { readonly kind: "config-panel" }
  | { readonly kind: "settings"; readonly settings: CliSettings; readonly blocks: readonly Block[] };

export interface CommandInput {
  readonly args: readonly string[];
  readonly rest: string;
}

export interface CommandContext {
  readonly data: CliData;
  readonly now: Date;
  readonly settings: CliSettings;
  readonly registry: Registry;
  readonly random: () => number;
}

export type Executor = (input: CommandInput, context: CommandContext) => CommandEffect;

export type CommandGroup = "Explore" | "AI" | "Session";

export interface Command {
  readonly name: string;
  readonly aliases: readonly string[];
  readonly usage: string;
  readonly summary: string;
  readonly group: CommandGroup;
  readonly plugin: string;
  readonly enabled: boolean;
  readonly argOptions: ((data: CliData) => readonly string[]) | undefined;
  readonly run: Executor;
}

export interface Registry {
  readonly all: readonly Command[];
  readonly commands: readonly Command[];
}

const STATS_TARGETS: readonly StatsTarget[] = ["leetcode", "codeforces", "github"];
export const BAR_WIDTH = 16;
const RECENT_CONTESTS = 5;
const TOP_REPOSITORIES = 5;

export const SHORTCUTS: readonly (readonly [string, string])[] = [
  ["Enter", "run the command or ask the agent"],
  ["Shift+Enter", "new line"],
  ["Tab / →", "accept the suggestion"],
  ["↑ ↓", "move in the menu, or recall earlier input"],
  ["Esc / Ctrl+C", "close the menu, or stop an answer"],
  ["Ctrl+L", "clear the screen"],
  ["Ctrl+U", "clear the line"],
  ["Shift+Tab", "cycle mode: default, auto-run, plan"],
];

function print(...blocks: readonly Block[]): CommandEffect {
  return { kind: "print", blocks };
}

function notFound(kind: string, query: string, options: readonly string[], command: string): CommandEffect {
  return print(
    error(`No ${kind} matches "${query}".`),
    hint(`Try ${command} ${options.map((option) => `"${option}"`).join(", ")}`),
  );
}

function period(start: string, end: string): string {
  return `${formatYearMonth(start)} – ${formatYearMonth(end)}`;
}

function linkedinUrl(data: CliData): string | null {
  return data.leetcode.find((account) => account.linkedin_url !== null)?.linkedin_url ?? null;
}

function socialPairs(data: CliData): (readonly [string, Line])[] {
  const pairs: (readonly [string, Line])[] = [];
  const email = data.profile.profile_details.email;
  pairs.push(["Email", [link(email, `mailto:${email}`)]]);
  const githubLinks = data.professional.github_links;
  for (const [index, url] of githubLinks.entries()) {
    pairs.push([githubLinks.length > 1 ? `GitHub ${index + 1}` : "GitHub", [link(profileHandle(url), url)]]);
  }
  const linkedin = linkedinUrl(data);
  if (linkedin !== null) {
    pairs.push(["LinkedIn", [link(profileHandle(linkedin), linkedin)]]);
  }
  if (data.professional.twitter_url !== null) {
    pairs.push(["X", [link(profileHandle(data.professional.twitter_url), data.professional.twitter_url)]]);
  }
  for (const url of data.professional.leetcode_links) {
    pairs.push(["LeetCode", [link(profileHandle(url), url)]]);
  }
  for (const url of data.professional.codeforces_links) {
    pairs.push(["Codeforces", [link(profileHandle(url), url)]]);
  }
  return pairs;
}

export function skillSummary(registry: Registry, data: CliData, settings: CliSettings): string {
  const enabledPlugins = data.manifest.plugins.filter((plugin) => isPluginEnabled(settings, plugin.name)).length;
  return `${registry.commands.length} of ${registry.all.length} skills on · ${data.manifest.plugins.length} plugins (${enabledPlugins} on)`;
}

function help(_input: CommandInput, { registry, data, settings }: CommandContext): CommandEffect {
  const groups: readonly CommandGroup[] = ["Explore", "AI", "Session"];
  const blocks: Block[] = [{ kind: "heading", text: "Skills", meta: skillSummary(registry, data, settings) }];
  for (const group of groups) {
    const commands = registry.commands.filter((command) => command.group === group);
    if (commands.length === 0) {
      continue;
    }
    blocks.push({ kind: "heading", text: group });
    blocks.push({ kind: "pairs", pairs: commands.map((command) => [command.usage, [span(command.summary, "muted")]]) });
  }
  blocks.push({ kind: "heading", text: "Shortcuts" });
  blocks.push({ kind: "pairs", pairs: SHORTCUTS.map(([keys, action]) => [keys, [span(action, "muted")]]) });
  blocks.push(hint("Anything without a leading / goes to the agent. /plugins adds more skills."));
  return print(...blocks);
}

function config({ args }: CommandInput, { data, settings }: CommandContext): CommandEffect {
  const [key, value] = args;
  if (key === undefined) {
    return { kind: "config-panel" };
  }
  if (value === undefined) {
    const setting = data.manifest.settings.find((candidate) => candidate.key.toLowerCase() === key.toLowerCase());
    if (setting === undefined) {
      return print(
        error(`Unknown setting "${key}".`),
        hint(`Settings: ${data.manifest.settings.map((item) => item.key).join(", ")}`),
      );
    }
    return print({
      kind: "pairs",
      pairs: [
        [setting.label, [span(settingValue(settings, setting.key), "text", true)]],
        ["Options", [span(setting.options.join(" · "), "muted")]],
        ["", [span(setting.summary, "faint")]],
      ],
    });
  }
  const change = changeSetting(settings, data.manifest, key, value);
  return change.ok
    ? {
        kind: "settings",
        settings: change.settings,
        blocks: [{ kind: "lines", lines: [[span(change.message, "success")]] }],
      }
    : print(error(change.message));
}

function plugins({ args }: CommandInput, { data, settings, registry }: CommandContext): CommandEffect {
  const [action, name] = args;
  if (action === undefined) {
    return print(
      { kind: "heading", text: "Plugins", meta: skillSummary(registry, data, settings) },
      {
        kind: "table",
        rows: data.manifest.plugins.map((plugin) => {
          const enabled = isPluginEnabled(settings, plugin.name);
          const count = registry.all.filter((command) => command.plugin === plugin.name).length;
          return [
            [span(enabled ? "●" : "○", enabled ? "success" : "faint")],
            [span(plugin.name, "text", true), span(plugin.removable ? "" : " (always on)", "faint")],
            [span(`${count} skill${count === 1 ? "" : "s"} · ${plugin.summary}`, "muted")],
          ];
        }),
      },
      hint("/plugins enable <name> or /plugins disable <name>"),
    );
  }
  const verb = action.toLowerCase();
  if ((verb !== "enable" && verb !== "disable") || name === undefined) {
    return print(error("Usage: /plugins enable <name> or /plugins disable <name>"));
  }
  const change = changePlugin(settings, data.manifest, name, verb === "enable");
  return change.ok
    ? {
        kind: "settings",
        settings: change.settings,
        blocks: [{ kind: "lines", lines: [[span(change.message, "success")]] }],
      }
    : print(error(change.message));
}

function neofetch(_input: CommandInput, { data, now }: CommandContext): CommandEffect {
  const { profile } = data;
  const current = profile.experience.find(isCurrent) ?? profile.experience[0];
  const initials = data.ownerName
    .split(/\s+/)
    .map((part) => part[0] ?? "")
    .join("")
    .toUpperCase();
  const languages = Object.values(profile.skills_by_category)[0] ?? [];
  const codeforces = data.codeforces[0];
  const leetcode = data.leetcode[0];
  return print(
    { kind: "heading", text: `${data.ownerName.split(" ")[0]?.toLowerCase() ?? "me"}@portfolio` },
    {
      kind: "table",
      rows: [
        [
          [span(`╭───╮`, "accent")],
          [span("OS", "faint")],
          [span("Software engineer, backend and distributed systems")],
        ],
        [
          [span(`│${initials.padEnd(3).slice(0, 3)}│`, "accent")],
          [span("Role", "faint")],
          [span(current === undefined ? "—" : `${current.title} at ${current.company}`)],
        ],
        [
          [span("╰───╯", "accent")],
          [span("Uptime", "faint")],
          [span(current === undefined ? "—" : experienceDuration(current, now))],
        ],
        [[span("")], [span("Languages", "faint")], [span(languages.slice(0, 6).join(", "))]],
        [[span("")], [span("Projects", "faint")], [span(String(profile.projects.length))]],
        [
          [span("")],
          [span("Codeforces", "faint")],
          [
            span(
              codeforces?.current_rating === null || codeforces === undefined ? "—" : String(codeforces.current_rating),
            ),
          ],
        ],
        [
          [span("")],
          [span("LeetCode", "faint")],
          [span(leetcode?.total_solved === null || leetcode === undefined ? "—" : `${leetcode.total_solved} solved`)],
        ],
      ],
    },
  );
}

function fortune(_input: CommandInput, { data, random }: CommandContext): CommandEffect {
  const fortunes = data.manifest.fortunes;
  const pick = fortunes[Math.floor(random() * fortunes.length)];
  return pick === undefined
    ? print(hint("No fortunes today."))
    : print({ kind: "lines", lines: [[span(`“${pick}”`)]] });
}

function whoami(_input: CommandInput, { data, now }: CommandContext): CommandEffect {
  const { profile } = data;
  const current = profile.experience.find(isCurrent) ?? profile.experience[0];
  const blocks: Block[] = [{ kind: "heading", text: data.ownerName, meta: "whoami" }];
  if (current !== undefined) {
    blocks.push({
      kind: "lines",
      lines: [
        [
          span(current.title, "text", true),
          span(" at ", "muted"),
          span(current.company, "text", true),
          span(` · ${current.location} · ${experienceDuration(current, now)}`, "faint"),
        ],
      ],
    });
  }
  blocks.push({
    kind: "pairs",
    pairs: [
      [
        "Roles",
        [
          span(
            `${profile.experience.length} across ${new Set(profile.experience.map((job) => job.company)).size} companies`,
          ),
        ],
      ],
      ["Projects", [span(String(profile.projects.length))]],
      ["Languages", [span(profile.languages.join(", "))]],
      ...socialPairs(data),
    ],
  });
  blocks.push(hint("Next: /experience, /projects, /skills, or just ask a question."));
  return print(...blocks);
}

function experience({ rest }: CommandInput, { data, now }: CommandContext): CommandEffect {
  const jobs = data.profile.experience;
  if (rest === "") {
    return print(
      { kind: "heading", text: "Experience", meta: `${jobs.length} roles` },
      {
        kind: "table",
        rows: jobs.map((job) => [
          [span(isCurrent(job) ? "●" : "○", isCurrent(job) ? "success" : "faint")],
          [span(job.title, "text", true), span(" · ", "faint"), span(job.company, "muted")],
          [span(`${period(job.start_date, job.end_date)} · ${experienceDuration(job, now)}`, "faint")],
        ]),
      },
      hint("Details: /experience <company>"),
    );
  }
  const match = findByName(jobs, rest, (item) => item.company);
  if (match === undefined) {
    return notFound("company", rest, companies(data), "/experience");
  }
  return print(
    ...jobs
      .filter((job) => job.company === match.company)
      .flatMap((job): Block[] => [
        { kind: "heading", text: `${job.title} · ${job.company}`, meta: isCurrent(job) ? "current" : undefined },
        {
          kind: "pairs",
          pairs: [
            ["Period", [span(`${period(job.start_date, job.end_date)} · ${experienceDuration(job, now)}`)]],
            ["Type", [span(job.employment_type)]],
            ["Location", [span(job.location)]],
          ],
        },
        { kind: "list", items: job.description.map((line) => [span(line)]) },
        { kind: "chips", items: job.technologies },
      ]),
  );
}

function companies(data: CliData): readonly string[] {
  return [...new Set(data.profile.experience.map((job) => job.company))];
}

function projects({ rest }: CommandInput, { data }: CommandContext): CommandEffect {
  const items = data.profile.projects;
  if (rest === "") {
    return print(
      { kind: "heading", text: "Projects", meta: `${items.length} shipped` },
      {
        kind: "table",
        rows: items.map((project, index) => [
          [span(String(index + 1).padStart(2, "0"), "faint")],
          [span(project.name, "text", true)],
          [span(String(project.year), "faint")],
        ]),
      },
      hint("Details: /projects <name>"),
    );
  }
  const project = findByName(items, rest, (item) => item.name);
  if (project === undefined) {
    return notFound(
      "project",
      rest,
      items.map((item) => item.name.split(/\s[-–—:]\s/)[0] ?? item.name),
      "/projects",
    );
  }
  return print(
    { kind: "heading", text: project.name, meta: String(project.year) },
    { kind: "lines", lines: [[link(project.link, project.link)]] },
    { kind: "list", items: project.description.map((line) => [span(line)]) },
    { kind: "chips", items: project.technologies },
  );
}

function skills({ rest }: CommandInput, { data }: CommandContext): CommandEffect {
  const categories = Object.entries(data.profile.skills_by_category);
  if (rest === "") {
    return print(
      { kind: "heading", text: "Skills", meta: `${categories.length} areas` },
      { kind: "pairs", pairs: categories.map(([category, items]) => [category, [span(items.join(", "), "muted")]]) },
    );
  }
  const match = findByName(categories, rest, ([category]) => category);
  if (match === undefined) {
    return notFound(
      "skill area",
      rest,
      categories.map(([category]) => category),
      "/skills",
    );
  }
  return print(
    { kind: "heading", text: match[0], meta: `${match[1].length} skills` },
    { kind: "chips", items: match[1] },
  );
}

function education(_input: CommandInput, { data }: CommandContext): CommandEffect {
  return print(
    { kind: "heading", text: "Education" },
    ...data.profile.education.map(
      (entry): Block => ({
        kind: "pairs",
        pairs: [
          [entry.institution, [span(`${entry.degree}, ${entry.field}`, "text", true)]],
          ["", [span(`${period(entry.start_date, entry.end_date)} · ${entry.grade}`, "muted")]],
        ],
      }),
    ),
  );
}

function achievements(_input: CommandInput, { data }: CommandContext): CommandEffect {
  return print(
    { kind: "heading", text: "Achievements", meta: String(data.profile.achievements.length) },
    { kind: "list", items: data.profile.achievements.map((item) => [span(item)]) },
  );
}

function stats({ rest }: CommandInput): CommandEffect {
  const target = rest.toLowerCase();
  if (target === "") {
    return { kind: "stats", target: "all" };
  }
  const match = STATS_TARGETS.find((option) => option.startsWith(target));
  if (match === undefined) {
    return print(error(`Unknown platform "${rest}".`), hint("Try /stats leetcode, /stats codeforces or /stats github"));
  }
  return { kind: "stats", target: match };
}

function resume(_input: CommandInput, { data }: CommandContext): CommandEffect {
  return {
    kind: "open-url",
    url: data.resumeUrl,
    blocks: [
      {
        kind: "lines",
        lines: [[span("Opening the résumé (PDF) in a new tab… ", "muted"), link("résumé", data.resumeUrl)]],
      },
    ],
  };
}

function contact({ rest }: CommandInput, { data }: CommandContext): CommandEffect {
  const email = data.profile.profile_details.email;
  if (rest.toLowerCase() === "mail") {
    return {
      kind: "open-url",
      url: `mailto:${email}`,
      blocks: [{ kind: "lines", lines: [[span("Opening your mail app… ", "muted"), link(email, `mailto:${email}`)]] }],
    };
  }
  return print(
    { kind: "heading", text: "Contact" },
    { kind: "pairs", pairs: socialPairs(data) },
    hint("/contact mail opens your mail app, or use the form on the portfolio."),
  );
}

function ask({ rest }: CommandInput): CommandEffect {
  if (rest === "") {
    return print(error("Ask what? e.g. /ask what is his strongest project?"));
  }
  return { kind: "ask", question: rest };
}

function openChat({ rest }: CommandInput): CommandEffect {
  const index = Number(rest);
  if (!Number.isInteger(index) || index < 1) {
    return print(error("Usage: /open <n>, where n is a number from /history"));
  }
  return { kind: "open-chat", index };
}

function goBack(): CommandEffect {
  return {
    kind: "navigate",
    href: "/",
    blocks: [{ kind: "lines", lines: [[span("Returning to the portfolio…", "muted")]] }],
  };
}

const EXECUTORS: Readonly<Record<string, Executor>> = {
  help,
  whoami,
  config,
  plugins,
  clear: () => ({ kind: "clear" }),
  "go-back": goBack,
  experience,
  projects,
  skills,
  education,
  achievements,
  resume,
  contact,
  stats,
  ask,
  history: () => ({ kind: "list-chats" }),
  open: openChat,
  new: () => ({ kind: "new-chat" }),
  neofetch,
  fortune,
};

const ARG_SOURCES: Readonly<Record<CliArgSource, (data: CliData) => readonly string[]>> = {
  none: () => [],
  companies,
  projects: (data) => data.profile.projects.map((project) => project.name),
  skillAreas: (data) => Object.keys(data.profile.skills_by_category),
  platforms: () => STATS_TARGETS,
  mail: () => ["mail"],
  settings: (data) =>
    data.manifest.settings.flatMap((setting) => setting.options.map((option) => `${setting.key} ${option}`)),
  plugins: (data) =>
    data.manifest.plugins.flatMap((plugin) =>
      plugin.removable ? [`enable ${plugin.name}`, `disable ${plugin.name}`] : [`enable ${plugin.name}`],
    ),
};

export function executorNames(): readonly string[] {
  return Object.keys(EXECUTORS);
}

export function buildRegistry(manifest: CliManifest, settings: CliSettings): Registry {
  const all = manifest.skills.flatMap((skill): Command[] => {
    const run = EXECUTORS[skill.name];
    if (run === undefined) {
      return [];
    }
    return [
      {
        name: skill.name,
        aliases: skill.aliases,
        usage: skill.usage,
        summary: skill.summary,
        group: skill.group,
        plugin: skill.plugin,
        enabled: isPluginEnabled(settings, skill.plugin),
        argOptions: skill.arg_source === "none" ? undefined : ARG_SOURCES[skill.arg_source],
        run,
      },
    ];
  });
  return { all, commands: all.filter((command) => command.enabled) };
}

export function findCommand(registry: Registry, name: string): Command | undefined {
  const wanted = name.toLowerCase();
  return registry.all.find((command) => command.name === wanted || command.aliases.includes(wanted));
}

export function closestCommand(registry: Registry, name: string): Command | undefined {
  const wanted = name.toLowerCase();
  let best: { readonly command: Command; readonly distance: number } | undefined;
  for (const command of registry.commands) {
    for (const candidate of [command.name, ...command.aliases]) {
      const distance = editDistance(wanted, candidate);
      if (distance <= 2 && (best === undefined || distance < best.distance)) {
        best = { command, distance };
      }
    }
  }
  return best?.command;
}

export function editDistance(left: string, right: string): number {
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let row = 1; row <= left.length; row += 1) {
    const current = [row];
    for (let column = 1; column <= right.length; column += 1) {
      const substitution = (previous[column - 1] ?? 0) + (left[row - 1] === right[column - 1] ? 0 : 1);
      current.push(Math.min((previous[column] ?? 0) + 1, (current[column - 1] ?? 0) + 1, substitution));
    }
    previous = current;
  }
  return previous[right.length] ?? 0;
}

export function runCommand(name: string, input: CommandInput, context: CommandContext): CommandEffect {
  const command = findCommand(context.registry, name);
  if (command?.enabled === true) {
    return command.run(input, context);
  }
  if (command !== undefined) {
    return print(
      error(`/${command.name} is part of the ${command.plugin} plugin, which is off.`),
      hint(`Turn it on with /plugins enable ${command.plugin}`),
    );
  }
  const closest = closestCommand(context.registry, name);
  return print(
    error(`Unknown command /${name}.`),
    hint(closest === undefined ? "Type /help to see every skill." : `Did you mean ${closest.usage}?`),
  );
}

export function statsBlocks(target: StatsTarget, live: LiveStats): readonly Block[] {
  const blocks: Block[] = [];
  if (target === "all" || target === "leetcode") {
    blocks.push(...live.leetcode.flatMap(leetcodeBlocks));
  }
  if (target === "all" || target === "codeforces") {
    blocks.push(...live.codeforces.flatMap(codeforcesBlocks));
  }
  if (target === "all" || target === "github") {
    blocks.push(...live.github.flatMap(githubBlocks));
  }
  return blocks;
}

function optional(value: number | null, format: (value: number) => string = formatGrouped): string {
  return value === null ? "—" : format(value);
}

function leetcodeBlocks(account: LiveStats["leetcode"][number]): readonly Block[] {
  const total = account.total_solved ?? 0;
  const levels: readonly (readonly [string, number | null])[] = [
    ["Easy", account.easy_solved],
    ["Medium", account.medium_solved],
    ["Hard", account.hard_solved],
  ];
  return [
    { kind: "heading", text: `LeetCode · @${account.username}`, meta: `${optional(account.total_solved)} solved` },
    {
      kind: "bars",
      bars: levels.map(([label, value]) => ({ label, value: value ?? 0, max: total, caption: optional(value) })),
    },
    {
      kind: "pairs",
      pairs: [
        [
          "Contest rating",
          [
            span(
              optional(account.contest_rating, (value) => formatGrouped(Math.round(value))),
              "text",
              true,
            ),
          ],
        ],
        ["Global rank", [span(optional(account.contest_global_ranking))]],
        ["Streak", [span(`${optional(account.current_streak)} days`)]],
        ["Active days", [span(optional(account.total_active_days))]],
      ],
    },
  ];
}

function codeforcesBlocks(account: LiveStats["codeforces"][number]): readonly Block[] {
  const rank = account.current_rating === null ? "Unrated" : codeforcesRank(account.current_rating).title;
  const recent = account.rating_history.slice(-RECENT_CONTESTS).reverse();
  return [
    { kind: "heading", text: `Codeforces · ${account.handle}`, meta: rank },
    {
      kind: "pairs",
      pairs: [
        ["Rating", [span(optional(account.current_rating), "text", true)]],
        ["Peak", [span(optional(account.max_rating))]],
        ["Contests", [span(formatGrouped(account.contests_count))]],
      ],
    },
    ...(recent.length === 0
      ? []
      : [
          {
            kind: "table",
            rows: recent.map((change): readonly Line[] => {
              const delta = change.new_rating - change.old_rating;
              return [
                [span(`${delta >= 0 ? "+" : ""}${delta}`, delta >= 0 ? "success" : "danger", true)],
                [span(String(change.new_rating))],
                [span(change.contest_name, "muted")],
              ];
            }),
          } satisfies Block,
        ]),
  ];
}

function githubBlocks(account: LiveStats["github"][number]): readonly Block[] {
  const top = [...account.repositories].sort((left, right) => right.stars - left.stars).slice(0, TOP_REPOSITORIES);
  return [
    { kind: "heading", text: `GitHub · @${account.username}`, meta: `${formatGrouped(account.public_repos)} repos` },
    {
      kind: "pairs",
      pairs: [
        ["Followers", [span(formatGrouped(account.followers))]],
        ["Profile", [link(account.html_url, account.html_url)]],
      ],
    },
    ...(top.length === 0
      ? []
      : [
          {
            kind: "table",
            rows: top.map((repository): readonly Line[] => [
              [link(repository.name, repository.html_url)],
              [span(`★ ${repository.stars}`, "muted")],
              [span(repository.language ?? "—", "faint")],
            ]),
          } satisfies Block,
        ]),
  ];
}
