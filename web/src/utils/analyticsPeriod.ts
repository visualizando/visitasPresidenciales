import type {ChartPeriod} from "../components/ChartPeriodFilter";
import type {AccessEvent, Analytics} from "../types";

export const CURRENT_PRESIDENCY_START = "2023-01-01";

export function eventsForChartPeriod(events: AccessEvent[], period: ChartPeriod) {
  if (period === "all") return events;
  return events.filter((event) => {
    const date = event.occurred_at ?? event.entered_at ?? event.exited_at;
    return date != null && date.slice(0, 10) >= CURRENT_PRESIDENCY_START;
  });
}

export function analyticsForChartPeriod(analytics: Analytics | null, period: ChartPeriod): Analytics | null {
  if (!analytics || period === "all") return analytics;
  const current = analytics.current_presidency;
  return {
    ...analytics,
    daily: analytics.daily.filter((point) => point.date >= CURRENT_PRESIDENCY_START),
    monthly: analytics.monthly.filter((point) => point.month >= CURRENT_PRESIDENCY_START.slice(0, 7)),
    heatmap: current?.heatmap ?? [],
    purposes: current?.purposes ?? [],
    milei_casa_rosada_days: analytics.milei_casa_rosada_days?.filter((date) => date >= CURRENT_PRESIDENCY_START),
    coverage: {...analytics.coverage, first_date: current?.start_date ?? CURRENT_PRESIDENCY_START},
  };
}
