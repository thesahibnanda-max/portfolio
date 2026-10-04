import type {
  CliManifest,
  CodeforcesAccount,
  GitHubAccount,
  LeetcodeAccount,
  Professional,
  Profile,
} from "../api/schemas";

export type LeetcodeSummary = Pick<
  LeetcodeAccount,
  | "username"
  | "total_solved"
  | "easy_solved"
  | "medium_solved"
  | "hard_solved"
  | "contest_rating"
  | "contest_global_ranking"
  | "current_streak"
  | "total_active_days"
  | "linkedin_url"
>;

export interface LiveStats {
  readonly leetcode: readonly LeetcodeSummary[];
  readonly codeforces: readonly CodeforcesAccount[];
  readonly github: readonly GitHubAccount[];
}

export interface CliData extends LiveStats {
  readonly ownerName: string;
  readonly profile: Profile;
  readonly professional: Professional;
  readonly resumeUrl: string;
  readonly builtAt: string;
  readonly manifest: CliManifest;
}

export function summarizeLeetcode(account: LeetcodeAccount): LeetcodeSummary {
  return {
    username: account.username,
    total_solved: account.total_solved,
    easy_solved: account.easy_solved,
    medium_solved: account.medium_solved,
    hard_solved: account.hard_solved,
    contest_rating: account.contest_rating,
    contest_global_ranking: account.contest_global_ranking,
    current_streak: account.current_streak,
    total_active_days: account.total_active_days,
    linkedin_url: account.linkedin_url,
  };
}
