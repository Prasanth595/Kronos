import type { PredictionResponse } from "../types";

export type PredictionMetrics = {
  mae: number;
  rmse: number;
  mape: number;
};

const EMPTY_METRICS: PredictionMetrics = {
  mae: Number.NaN,
  rmse: Number.NaN,
  mape: Number.NaN,
};

export function getMetrics(result: PredictionResponse | null): PredictionMetrics {
  if (!result?.prediction_results.length || !result.actual_data.length) {
    return EMPTY_METRICS;
  }

  const pairs = result.prediction_results
    .map((prediction, index) => ({
      actual: result.actual_data[index],
      prediction,
    }))
    .filter(({ actual }) => Boolean(actual));

  if (!pairs.length) return EMPTY_METRICS;

  const absoluteErrors = pairs.flatMap(({ actual, prediction }) => [
    Math.abs(prediction.open - actual.open),
    Math.abs(prediction.high - actual.high),
    Math.abs(prediction.low - actual.low),
    Math.abs(prediction.close - actual.close),
  ]);

  const squaredErrors = absoluteErrors.map((value) => value ** 2);
  const percentageErrors = pairs.flatMap(({ actual, prediction }) => [
    percentageError(prediction.open, actual.open),
    percentageError(prediction.high, actual.high),
    percentageError(prediction.low, actual.low),
    percentageError(prediction.close, actual.close),
  ]);

  return {
    mae: mean(absoluteErrors),
    rmse: Math.sqrt(mean(squaredErrors)),
    mape: mean(percentageErrors) * 100,
  };
}

function mean(values: number[]) {
  const validValues = values.filter(Number.isFinite);
  if (!validValues.length) return Number.NaN;

  return validValues.reduce((sum, value) => sum + value, 0) / validValues.length;
}

function percentageError(predicted: number, actual: number) {
  if (!Number.isFinite(actual) || actual === 0) return Number.NaN;

  return Math.abs((predicted - actual) / actual);
}
