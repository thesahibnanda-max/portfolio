import type { z } from "zod";
import { ApiClient } from "../lib/api/client";
import {
  accountsSchema,
  codeforcesAccountSchema,
  githubAccountSchema,
  leetcodeAccountSchema,
  personalitySchema,
  professionalSchema,
  profileSchema,
} from "../lib/api/schemas";
import { BACKEND_BASE_URL } from "../lib/config";

const client = new ApiClient(BACKEND_BASE_URL);

function load<T extends z.ZodType>(path: string, schema: T): Promise<z.infer<T>> {
  return client.request(path, schema);
}

export const [profile, personality, professional, leetcode, codeforces, github] = await Promise.all([
  load("/details/profile", profileSchema),
  load("/details/personality", personalitySchema),
  load("/details/professional", professionalSchema),
  load("/details/leetcode", accountsSchema(leetcodeAccountSchema)),
  load("/details/codeforces", accountsSchema(codeforcesAccountSchema)),
  load("/details/github", accountsSchema(githubAccountSchema)),
]);

export const profileImageUrl = client.url(profile.profile_image_url);
export const resumeUrl = client.url(professional.resume_link);
export const profileImage = await client.requestBytes(profile.profile_image_url);

export const builtAt = new Date();
