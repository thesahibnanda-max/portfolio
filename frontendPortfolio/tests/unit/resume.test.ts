import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { ApiClient } from "../../src/lib/api/client";
import { professionalSchema } from "../../src/lib/api/schemas";

const PROFESSIONAL = JSON.parse(await readFile(new URL("../fixtures/api/professional.json", import.meta.url), "utf8"));

describe("professionalSchema", () => {
  it("requires the résumé as a relative, versioned API path", () => {
    expect(professionalSchema.parse(PROFESSIONAL).resume_link).toMatch(/^\/details\/resume\?v=[0-9a-f]{16}$/);
    expect(
      professionalSchema.safeParse({ ...PROFESSIONAL, resume_link: "https://storage.test/resume.pdf" }).success,
    ).toBe(false);
    const { resume_link: _ignored, ...withoutResume } = PROFESSIONAL;
    expect(professionalSchema.safeParse(withoutResume).success).toBe(false);
  });

  it("resolves the résumé against the API base url", () => {
    const { resume_link } = professionalSchema.parse(PROFESSIONAL);

    expect(new ApiClient("https://api.example.test/").url(resume_link)).toBe(`https://api.example.test${resume_link}`);
  });
});
