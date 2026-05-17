export type ModelInfo = {
  name: string;
  model_id: string;
  tokenizer_id: string;
  context_length: number;
  params: string;
  description: string;
};

export type DataFile = {
  name: string;
  path: string;
  size: string;
};

export type DataInfo = {
  rows: number;
  columns: string[];
  start_date: string;
  end_date: string;
  price_range: {
    min: number;
    max: number;
  };
  prediction_columns: string[];
  timeframe: string;
};

export type PredictionPoint = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
};

export type PredictionResponse = {
  success: boolean;
  prediction_type: string;
  chart: string;
  prediction_results: PredictionPoint[];
  actual_data: PredictionPoint[];
  has_comparison: boolean;
  message: string;
};

export type ServerHealth = {
  success: boolean;
  service: string;
  status: string;
  model_available: boolean;
  model_loaded: boolean;
};

export type StatusMessage = {
  type: "info" | "success" | "warning" | "error";
  text: string;
};

export type ServerStatus = "checking" | "running" | "offline" | "loading-model";

export type LoadingAction = "models" | "model" | "unload" | "data" | "predict" | null;
