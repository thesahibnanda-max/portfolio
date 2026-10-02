import { describe, expect, it } from "vitest";
import type { Experience } from "../../src/lib/api/schemas";
import {
  codeforcesRank,
  experienceDuration,
  formatDuration,
  formatYearMonth,
  monthsBetween,
  parseYearMonth,
  profileHandle,
} from "../../src/lib/format";

const role = (start: string, end: string): Experience => ({
  company: "CheQ",
  location: "Bengaluru",
  employment_type: "Full-time",
  title: "SDE",
  start_date: start,
  end_date: end,
  description: [],
  technologies: [],
});

describe("dates", () => {
  it("parses and formats year-months", () => {
    expect(parseYearMonth("2026-09")).toEqual({ year: 2026, month: 9 });
    expect(formatYearMonth("2025-06")).toBe("Jun 2025");
    expect(formatYearMonth("Present")).toBe("Present");
  });

  it("rejects malformed values instead of guessing", () => {
    expect(() => parseYearMonth("2026-13")).toThrow(RangeError);
    expect(() => parseYearMonth("Sept 2026")).toThrow(RangeError);
  });

  it("counts both the first and last month", () => {
    expect(monthsBetween({ year: 2025, month: 6 }, { year: 2026, month: 6 })).toBe(13);
    expect(formatDuration(13)).toBe("1y 1m");
    expect(formatDuration(12)).toBe("1y");
    expect(formatDuration(0)).toBe("<1m");
  });

  it("measures a current role up to now in UTC", () => {
    expect(experienceDuration(role("2026-09", "Present"), new Date("2026-10-02T00:00:00Z"))).toBe("2m");
    expect(experienceDuration(role("2024-12", "2025-05"), new Date("2030-01-01T00:00:00Z"))).toBe("6m");
  });
});

describe("codeforcesRank", () => {
  it.each([
    [1987, "Candidate Master"],
    [1832, "Expert"],
    [1400, "Specialist"],
    [0, "Newbie"],
    [3100, "Legendary Grandmaster"],
  ])("maps %i to %s", (rating, title) => {
    expect(codeforcesRank(rating).title).toBe(title);
  });
});

describe("profileHandle", () => {
  it.each([
    ["https://github.com/thesahibnanda-max", "@thesahibnanda-max"],
    ["https://leetcode.com/u/imsahibnanda/", "@imsahibnanda"],
    ["https://codeforces.com/profile/shisukenohara", "@shisukenohara"],
    ["https://linkedin.com/in/sahib-nanda", "@sahib-nanda"],
    ["https://sahib.dev", "sahib.dev"],
  ])("turns %s into %s", (url, handle) => {
    expect(profileHandle(url)).toBe(handle);
  });
});
