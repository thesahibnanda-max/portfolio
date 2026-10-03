import { z } from "zod";

export const errorResponseSchema = z.object({
  status: z.number().int(),
  timestamp: z.string(),
  error: z.string(),
  message: z.string(),
  details: z.array(z.object({ field: z.string(), message: z.string() })).default([]),
});
export type ErrorResponse = z.infer<typeof errorResponseSchema>;

export const rawEnvelopeSchema = z.object({
  status: z.number().int(),
  timestamp: z.string(),
  data: z.unknown(),
});

export function envelopeSchema<T extends z.ZodType>(data: T) {
  return z.object({ status: z.number().int(), timestamp: z.string(), data });
}

const yearMonth = z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/);
const yearMonthOrPresent = z.union([yearMonth, z.literal("Present")]);

export const experienceSchema = z.object({
  company: z.string(),
  location: z.string(),
  employment_type: z.string(),
  title: z.string(),
  start_date: yearMonth,
  end_date: yearMonthOrPresent,
  description: z.array(z.string()),
  technologies: z.array(z.string()),
});
export type Experience = z.infer<typeof experienceSchema>;

export const projectSchema = z.object({
  name: z.string(),
  year: z.number().int(),
  link: z.url(),
  description: z.array(z.string()),
  technologies: z.array(z.string()),
});
export type Project = z.infer<typeof projectSchema>;

export const educationSchema = z.object({
  institution: z.string(),
  degree: z.string(),
  field: z.string(),
  start_date: yearMonth,
  end_date: yearMonthOrPresent,
  grade: z.string(),
});
export type Education = z.infer<typeof educationSchema>;

export const profileSchema = z.object({
  profile_details: z.object({ name: z.string(), email: z.email() }),
  profile_image_url: z.string().startsWith("/"),
  projects: z.array(projectSchema),
  languages: z.array(z.string()),
  achievements: z.array(z.string()),
  experience: z.array(experienceSchema),
  education: z.array(educationSchema),
  skills_by_category: z.record(z.string(), z.array(z.string())),
});
export type Profile = z.infer<typeof profileSchema>;

const titledSchema = z.object({ title: z.string(), genre: z.string() });

export const personalitySchema = z.object({
  personal_profile: z.object({
    personality: z.object({
      core_traits: z.array(z.string()),
      professional_traits: z.array(z.string()),
      work_preferences: z.object({
        preferred_domains: z.array(z.string()),
        engineering_values: z.array(z.string()),
      }),
      personal_values: z.array(z.string()),
    }),
    interests: z.object({
      sports: z.record(z.string(), z.object({ favorite_team: z.string(), favorite_player: z.string() })),
      fitness: z.array(z.string()),
      technology: z.array(z.string()),
    }),
    favorites: z.object({
      movies: z.array(titledSchema),
      games: z.array(titledSchema),
      artists: z.array(z.object({ name: z.string(), type: z.string() })),
    }),
    languages: z.array(z.object({ name: z.string(), proficiency: z.string() })),
  }),
});
export type Personality = z.infer<typeof personalitySchema>;

export const professionalSchema = z.object({
  leetcode_links: z.array(z.url()),
  codeforces_links: z.array(z.url()),
  github_links: z.array(z.url()),
  resume_link: z.string().startsWith("/"),
  profile_photo_links: z.array(z.url()),
  websites: z.array(z.url()),
  twitter_url: z.url().nullable().default(null),
});
export type Professional = z.infer<typeof professionalSchema>;

const countMap = z.record(z.string(), z.number().int());

export const leetcodeAccountSchema = z.object({
  username: z.string(),
  ranking: z.number().int().nullable(),
  total_solved: z.number().int().nullable(),
  easy_solved: z.number().int().nullable(),
  medium_solved: z.number().int().nullable(),
  hard_solved: z.number().int().nullable(),
  badges: z.array(z.string()),
  language_problems_solved: countMap,
  advanced_tags_solved: countMap,
  intermediate_tags_solved: countMap,
  fundamental_tags_solved: countMap,
  contest_rating: z.number().nullable(),
  contest_global_ranking: z.number().int().nullable(),
  current_streak: z.number().int().nullable(),
  total_active_days: z.number().int().nullable(),
  linkedin_url: z.url().nullable().default(null),
  about_me: z.string().nullable().default(null),
});
export type LeetcodeAccount = z.infer<typeof leetcodeAccountSchema>;

export const ratingChangeSchema = z.object({
  contest_name: z.string(),
  rank: z.number().int(),
  old_rating: z.number().int(),
  new_rating: z.number().int(),
  contest_time: z.string().nullable(),
});
export type RatingChange = z.infer<typeof ratingChangeSchema>;

export const codeforcesAccountSchema = z.object({
  handle: z.string(),
  current_rating: z.number().int().nullable(),
  max_rating: z.number().int().nullable(),
  contests_count: z.number().int(),
  rating_history: z.array(ratingChangeSchema),
});
export type CodeforcesAccount = z.infer<typeof codeforcesAccountSchema>;

export const repositorySchema = z.object({
  name: z.string(),
  description: z.string().nullable(),
  html_url: z.url(),
  language: z.string().nullable(),
  stars: z.number().int(),
  forks: z.number().int(),
  updated_at: z.string(),
});
export type Repository = z.infer<typeof repositorySchema>;

export const githubAccountSchema = z.object({
  username: z.string(),
  name: z.string().nullable(),
  avatar_url: z.url().nullable(),
  bio: z.string().nullable(),
  public_repos: z.number().int(),
  followers: z.number().int(),
  following: z.number().int(),
  html_url: z.url(),
  repositories: z.array(repositorySchema),
});
export type GitHubAccount = z.infer<typeof githubAccountSchema>;

export function accountsSchema<T extends z.ZodType>(account: T) {
  return z.object({ accounts: z.array(account) });
}

export const sessionSchema = z.object({
  session_id: z.string(),
  created_at: z.string(),
  expires_at: z.string(),
});
export type Session = z.infer<typeof sessionSchema>;

export const chatSummarySchema = z.object({
  chat_id: z.string(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type ChatSummary = z.infer<typeof chatSummarySchema>;

export const storedMessageSchema = z.object({
  message_id: z.number().int(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  created_at: z.string(),
});
export type StoredMessage = z.infer<typeof storedMessageSchema>;

export const chatSchema = chatSummarySchema.extend({ messages: z.array(storedMessageSchema) });
export type Chat = z.infer<typeof chatSchema>;

export const chatListSchema = z.object({ chats: z.array(chatSummarySchema) });

export const queryScopeSchema = z.enum(["IN_SCOPE", "NOT_RELATED_TO_PORTFOLIO", "PROMPT_INJECTION", "UNSAFE"]);
export type QueryScope = z.infer<typeof queryScopeSchema>;

export const chatReplySchema = z.object({
  chat: chatSchema,
  answer: z.string(),
  scope: queryScopeSchema,
  required_contexts: z.array(z.string()).default([]),
});
export type ChatReply = z.infer<typeof chatReplySchema>;

export const streamTokenSchema = z.object({ text: z.string() });

export const contactResponseSchema = z.object({ status: z.literal("SENT"), reply_to: z.string(), sent_at: z.string() });
export type ContactResponse = z.infer<typeof contactResponseSchema>;
