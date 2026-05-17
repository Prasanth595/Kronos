import type { DataFile, DataInfo, ModelInfo, PredictionResponse, ServerHealth } from "../types";

type ApiError = {
  error?: string;
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const payload = (await response.json()) as T & ApiError;

  if (!response.ok) {
    throw new Error(payload.error ?? "Yêu cầu API thất bại");
  }

  return payload;
}

export async function fetchAvailableModels() {
  return requestJson<{ models: Record<string, ModelInfo>; model_available: boolean }>(
    "/api/available-models",
  );
}

export async function fetchDataFiles() {
  return requestJson<DataFile[]>("/api/data-files");
}

export async function fetchServerHealth() {
  return requestJson<ServerHealth>("/api/health", {
    cache: "no-store",
  });
}

export async function loadModel(modelKey: string, device: string) {
  return requestJson<{
    success: boolean;
    message: string;
    model_info: Pick<ModelInfo, "name" | "params" | "context_length" | "description">;
  }>("/api/load-model", {
    method: "POST",
    body: JSON.stringify({ model_key: modelKey, device }),
  });
}

export async function unloadModel() {
  return requestJson<{
    success: boolean;
    was_loaded: boolean;
    message: string;
  }>("/api/unload-model", {
    method: "POST",
  });
}

export async function loadDataFile(filePath: string) {
  return requestJson<{ success: boolean; data_info: DataInfo; message: string }>(
    "/api/load-data",
    {
      method: "POST",
      body: JSON.stringify({ file_path: filePath }),
    },
  );
}

export async function runPrediction(input: {
  file_path: string;
  lookback: number;
  pred_len: number;
  start_date: string;
  temperature: number;
  top_p: number;
  sample_count: number;
}) {
  return requestJson<PredictionResponse>("/api/predict", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
