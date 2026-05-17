import type { DataInfo } from "../types";
import { WINDOW_SIZE } from "./constants";

export function getWindowDates(dataInfo: DataInfo | null, startPercent: number) {
  if (!dataInfo || dataInfo.rows <= 0) {
    return { startDate: null, endDate: null };
  }

  const firstDate = new Date(dataInfo.start_date);
  const lastDate = new Date(dataInfo.end_date);

  if (Number.isNaN(firstDate.getTime()) || Number.isNaN(lastDate.getTime())) {
    return { startDate: null, endDate: null };
  }

  const maxStartIndex = Math.max(dataInfo.rows - WINDOW_SIZE, 0);
  const clampedPercent = Math.min(Math.max(startPercent, 0), 1);
  const startIndex = Math.round(maxStartIndex * clampedPercent);
  const intervalMs = dataInfo.rows > 1
    ? (lastDate.getTime() - firstDate.getTime()) / (dataInfo.rows - 1)
    : 0;

  return {
    startDate: new Date(firstDate.getTime() + startIndex * intervalMs),
    endDate: new Date(
      firstDate.getTime() + Math.min(startIndex + WINDOW_SIZE - 1, dataInfo.rows - 1) * intervalMs,
    ),
  };
}
