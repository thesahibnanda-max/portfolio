const ACTIVE = "skill-active";

function matches(element: HTMLElement, skill: string): boolean {
  return (element.dataset.tech ?? "").split("|").includes(skill);
}

function highlight(skill: string | null): void {
  document.documentElement.toggleAttribute("data-skill-focus", skill !== null);
  for (const element of document.querySelectorAll<HTMLElement>("[data-tech]")) {
    element.classList.toggle(ACTIVE, skill !== null && matches(element, skill));
  }
  for (const pill of document.querySelectorAll<HTMLElement>("[data-skill-pill], [data-skill]")) {
    const name = pill.dataset.skillPill ?? pill.dataset.skill;
    pill.classList.toggle(ACTIVE, skill !== null && name === skill);
  }
}

export function startSkillHighlights(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>("[data-skill]")) {
    const skill = button.dataset.skill ?? null;
    button.addEventListener("pointerenter", () => highlight(skill));
    button.addEventListener("focus", () => highlight(skill));
    button.addEventListener("pointerleave", () => highlight(null));
    button.addEventListener("blur", () => highlight(null));
  }
}
