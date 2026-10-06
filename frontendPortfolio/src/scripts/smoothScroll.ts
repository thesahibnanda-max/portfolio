import Lenis from "lenis";

export function startSmoothScroll(): void {
  const lenis = new Lenis({ duration: 1.1, anchors: { offset: -72 } });
  const frame = (time: number): void => {
    lenis.raf(time);
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}
