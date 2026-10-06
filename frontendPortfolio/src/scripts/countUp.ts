const DURATION_MS = 1400;

function easeOutExpo(progress: number): number {
  return progress === 1 ? 1 : 1 - 2 ** (-10 * progress);
}

export function animateCount(element: HTMLElement, target: number, decimals: number): void {
  const format = new Intl.NumberFormat("en", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  const start = performance.now();
  const step = (now: number): void => {
    const progress = Math.min(1, (now - start) / DURATION_MS);
    element.textContent = format.format(target * easeOutExpo(progress));
    if (progress < 1) {
      requestAnimationFrame(step);
    }
  };
  requestAnimationFrame(step);
}

export function startCountUps(): void {
  if (!("IntersectionObserver" in window)) {
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting || !(entry.target instanceof HTMLElement)) {
          continue;
        }
        observer.unobserve(entry.target);
        const target = Number(entry.target.dataset.count);
        if (Number.isFinite(target)) {
          animateCount(entry.target, target, Number(entry.target.dataset.decimals ?? "0"));
        }
      }
    },
    { threshold: 0.6 },
  );
  for (const element of document.querySelectorAll<HTMLElement>("[data-count]")) {
    observer.observe(element);
  }
}
