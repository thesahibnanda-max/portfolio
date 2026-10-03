import type { CodeforcesAccount, GitHubAccount, LeetcodeAccount, Professional, Profile } from "../api/schemas";

export interface CliData {
  readonly ownerName: string;
  readonly profile: Profile;
  readonly professional: Professional;
  readonly leetcode: readonly LeetcodeAccount[];
  readonly codeforces: readonly CodeforcesAccount[];
  readonly github: readonly GitHubAccount[];
  readonly resumeUrl: string;
  readonly builtAt: string;
}

export interface LiveStats {
  readonly leetcode: readonly LeetcodeAccount[];
  readonly codeforces: readonly CodeforcesAccount[];
  readonly github: readonly GitHubAccount[];
}
