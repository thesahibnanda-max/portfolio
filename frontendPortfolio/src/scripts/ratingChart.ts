import { z } from "zod";

const seriesSchema = z.array(z.tuple([z.number(), z.number()]));
const ACCENT = "#F5A524";
const AXIS = "rgba(255,255,255,0.35)";
const GRID = "rgba(255,255,255,0.05)";
const CHART_FONT = '11px "Geist Mono Variable", monospace';

export function mountRatingCharts(): void {
  const targets = document.querySelectorAll<HTMLElement>("[data-rating-chart]");
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && entry.target instanceof HTMLElement) {
          observer.unobserve(entry.target);
          void drawChart(entry.target).catch((error: unknown) => {
            console.warn("Rating chart could not be drawn", error);
          });
        }
      }
    },
    { rootMargin: "200px" },
  );
  for (const target of targets) {
    observer.observe(target);
  }
}

async function drawChart(target: HTMLElement): Promise<void> {
  const parsed = seriesSchema.safeParse(JSON.parse(target.dataset.ratingChart ?? "[]"));
  if (!parsed.success || parsed.data.length < 2) {
    return;
  }
  const { default: UPlot } = await import("uplot");
  const times = parsed.data.map(([time]) => time);
  const ratings = parsed.data.map(([, rating]) => rating);

  const chart = new UPlot(
    {
      width: target.clientWidth,
      height: target.clientHeight,
      cursor: { points: { size: 8, fill: ACCENT }, drag: { x: false, y: false } },
      legend: { show: false },
      scales: { x: { time: true } },
      axes: [
        { stroke: AXIS, grid: { stroke: GRID }, ticks: { show: false }, font: CHART_FONT },
        {
          stroke: AXIS,
          grid: { stroke: GRID },
          ticks: { show: false },
          font: CHART_FONT,
          size: 44,
        },
      ],
      series: [
        {},
        {
          label: "Rating",
          stroke: ACCENT,
          width: 2,
          points: { show: true, size: 4, fill: ACCENT, stroke: ACCENT },
          fill: (plot) => {
            const gradient = plot.ctx.createLinearGradient(0, plot.bbox.top, 0, plot.bbox.top + plot.bbox.height);
            gradient.addColorStop(0, "rgba(245,165,36,0.28)");
            gradient.addColorStop(1, "rgba(245,165,36,0)");
            return gradient;
          },
        },
      ],
    },
    [times, ratings],
    target,
  );

  new ResizeObserver(() => {
    chart.setSize({ width: target.clientWidth, height: target.clientHeight });
  }).observe(target);
}
