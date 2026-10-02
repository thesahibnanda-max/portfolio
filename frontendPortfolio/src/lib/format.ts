import type { Experience } from "./api/schemas";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

export interface YearMonth {
  readonly year: number;
  readonly month: number;
}

export function parseYearMonth(value: string): YearMonth {
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  if (match === null) {
    throw new RangeError(`Expected YYYY-MM, got ${value}`);
  }
  const month = Number(match[2]);
  if (month < 1 || month > 12) {
    throw new RangeError(`Month out of range in ${value}`);
  }
  return { year: Number(match[1]), month };
}

export function currentYearMonth(now: Date): YearMonth {
  return { year: now.getUTCFullYear(), month: now.getUTCMonth() + 1 };
}

export function formatYearMonth(value: string): string {
  if (value === "Present") {
    return "Present";
  }
  const { year, month } = parseYearMonth(value);
  return `${MONTHS[month - 1]} ${year}`;
}

export function monthsBetween(start: YearMonth, end: YearMonth): number {
  return (end.year - start.year) * 12 + (end.month - start.month) + 1;
}

export function formatDuration(totalMonths: number): string {
  const years = Math.floor(totalMonths / 12);
  const months = totalMonths % 12;
  const parts = [years > 0 ? `${years}y` : "", months > 0 ? `${months}m` : ""].filter((part) => part !== "");
  return parts.length === 0 ? "<1m" : parts.join(" ");
}

export function experienceDuration(experience: Experience, now: Date): string {
  const end = experience.end_date === "Present" ? currentYearMonth(now) : parseYearMonth(experience.end_date);
  return formatDuration(monthsBetween(parseYearMonth(experience.start_date), end));
}

export function isCurrent(experience: Experience): boolean {
  return experience.end_date === "Present";
}

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const grouped = new Intl.NumberFormat("en");

export function formatCompact(value: number): string {
  return compact.format(value);
}

export function formatGrouped(value: number): string {
  return grouped.format(value);
}

export interface CodeforcesRank {
  readonly title: string;
  readonly color: string;
}

const CODEFORCES_RANKS: readonly (readonly [number, CodeforcesRank])[] = [
  [3000, { title: "Legendary Grandmaster", color: "#FF3333" }],
  [2600, { title: "International Grandmaster", color: "#FF3333" }],
  [2400, { title: "Grandmaster", color: "#FF3333" }],
  [2300, { title: "International Master", color: "#FF8C00" }],
  [2100, { title: "Master", color: "#FF8C00" }],
  [1900, { title: "Candidate Master", color: "#C77DFF" }],
  [1600, { title: "Expert", color: "#5B8CFF" }],
  [1400, { title: "Specialist", color: "#03C1A6" }],
  [1200, { title: "Pupil", color: "#77DD77" }],
  [0, { title: "Newbie", color: "#A0A0A0" }],
];

export function codeforcesRank(rating: number): CodeforcesRank {
  for (const [floor, rank] of CODEFORCES_RANKS) {
    if (rating >= floor) {
      return rank;
    }
  }
  return { title: "Unrated", color: "#A0A0A0" };
}

export function hostname(url: string): string {
  return new URL(url).hostname.replace(/^www\./, "");
}

export function padIndex(index: number): string {
  return String(index + 1).padStart(2, "0");
}

export function profileHandle(url: string): string {
  const parsed = new URL(url);
  const segments = parsed.pathname
    .split("/")
    .filter((segment) => segment !== "" && segment !== "u" && segment !== "in" && segment !== "profile");
  const handle = segments.at(-1);
  return handle === undefined ? hostname(url) : `@${handle}`;
}
