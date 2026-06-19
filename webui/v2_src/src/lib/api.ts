import { fetchJson } from './http';
import { rlApi } from './rlApi';

export interface TrainingStatus {
  readonly run_name?: string;
  readonly status: string;
  readonly overall_percent?: number;
  readonly stage_count?: number;
  readonly stages: readonly TrainingStage[];
  readonly latest_stage?: TrainingStage;
  readonly dataset_summary?: DatasetSummary;
  readonly readiness?: {
    readonly level: 'waiting' | 'training' | 'ready';
    readonly label: string;
    readonly message: string;
    readonly predictor_started?: boolean;
    readonly predictor_complete?: boolean;
    readonly checkpoint_ready?: boolean;
  };
  readonly updated_at?: string;
  readonly default_training_refresh_seconds?: number;
  readonly generated_at?: string;
}

export interface DatasetSplitSummary {
  readonly name: 'train' | 'val' | 'test' | string;
  readonly sessions?: number;
  readonly first_session?: string | null;
  readonly last_session?: string | null;
  readonly groups?: number | null;
  readonly rows?: number | null;
  readonly possible_samples?: number | null;
  readonly current_target_samples?: number | null;
}

export interface DatasetSummary {
  readonly available: boolean;
  readonly dataset_dir?: string | null;
  readonly report_path?: string | null;
  readonly source_db?: string | null;
  readonly freq?: string | null;
  readonly regularize_1s?: boolean;
  readonly price_mode?: string | null;
  readonly horizon_seconds?: number | null;
  readonly lookback_window?: number | null;
  readonly predict_window?: number | null;
  readonly sample_window?: number | null;
  readonly features?: readonly string[];
  readonly time_features?: readonly string[];
  readonly range?: Record<string, string | null | undefined>;
  readonly counts?: {
    readonly selected_table_count?: string | number | null;
    readonly table_count?: number | null;
    readonly tables_with_rows?: number | null;
    readonly tables_zero_rows?: number | null;
    readonly exported_group_count?: number | null;
    readonly exported_row_count?: number | null;
    readonly regularized_groups?: number | null;
    readonly regularized_inserted_rows?: number | null;
  };
  readonly splits?: Record<string, DatasetSplitSummary>;
  readonly current_targets?: Record<string, number | null | undefined>;
  readonly warnings?: readonly string[];
  readonly message?: string;
}

export interface TrainingStage {
  readonly train_stage: string;
  readonly stage_index?: number;
  readonly stage_count?: number;
  readonly step?: number;
  readonly total_steps?: number;
  readonly overall_percent?: number;
  readonly stage_percent?: number;
  readonly eta_seconds?: number;
  readonly samples_per_second?: number;
  readonly last_loss?: number | null;
  readonly last_validation_loss?: number | null;
  readonly phase?: string | null;
  readonly validation_step?: number | null;
  readonly validation_total_steps?: number | null;
  readonly validation_samples?: number | null;
  readonly validation_fraction?: number | null;
  readonly epoch?: number | null;
  readonly epochs?: number | null;
  readonly status?: string;
  readonly updated_at?: string;
}

export interface HistoryPoint {
  readonly step: number;
  readonly loss: number;
  readonly learning_rate?: number;
  readonly epoch?: number;
  readonly epochs?: number;
}

export interface HistoryResponse {
  readonly points: readonly HistoryPoint[];
  readonly latest_point?: HistoryPoint & { readonly line?: string };
  readonly latest_progress?: Record<string, string | number | null | undefined>;
  readonly run_name?: string;
  readonly stage?: string;
  readonly source_log_path?: string;
}

export interface ArtifactsResponse {
  readonly checkpoint_file_count: number;
  readonly model_weight_file_count: number;
  readonly checkpoint_ready: boolean;
  readonly predictor_started: boolean;
  readonly label: string;
  readonly message: string;
  readonly recent_checkpoint_files: readonly ({ readonly path?: string; readonly name?: string } | string)[];
  readonly recent_model_weight_files: readonly ({ readonly path?: string; readonly name?: string } | string)[];
  readonly stages?: Record<string, { readonly checkpoint_ready: boolean }>;
  readonly run_name?: string;
}

export interface GpuResponse {
  readonly gpus: readonly {
    readonly name?: string;
    readonly utilization_gpu_percent?: number;
    readonly temperature_c?: number;
    readonly memory_used_percent?: number;
    readonly memory_used_mib?: number;
    readonly memory_total_mib?: number;
    readonly power_draw_available?: boolean;
    readonly power_draw_watts?: number;
    readonly power_limit_watts?: number;
  }[];
  readonly total_memory_used_percent?: number;
  readonly generated_at?: string;
  readonly available: boolean;
}

export interface SystemResponse {
  readonly available: boolean;
  readonly cpu?: {
    readonly utilization_percent?: number | null;
    readonly temperature_c?: number | null;
    readonly temperature_percent?: number | null;
  };
  readonly memory?: {
    readonly used_percent?: number | null;
    readonly total_bytes?: number | null;
    readonly available_bytes?: number | null;
  };
  readonly generated_at?: string;
}

export const api = {
  status: () => fetchJson<TrainingStatus>('/api/training/status'),
  history: (limit: number = 200) => fetchJson<HistoryResponse>(`/api/training/history?limit=${limit}`),
  artifacts: () => fetchJson<ArtifactsResponse>('/api/training/artifacts'),
  gpu: () => fetchJson<GpuResponse>('/api/training/gpu'),
  system: () => fetchJson<SystemResponse>('/api/training/system'),
  ...rlApi,
};
