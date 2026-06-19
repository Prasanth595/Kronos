import { fetchJson } from './http';

export type RlArtifactType =
  | 'contextual_bandit'
  | 'sb3_smoke'
  | 'cost_gate'
  | 'baseline'
  | 'episode_manifest'
  | 'opening_30m_rl_workflow'
  | 'portfolio_paper'
  | 'orderbook_rl_readiness'
  | string;

export type JsonScalar = string | number | boolean | null;
export type JsonValue = JsonScalar | readonly JsonValue[] | { readonly [key: string]: JsonValue };
export type JsonObject = { readonly [key: string]: JsonValue };
export type RlTableRow = JsonObject;

export interface RlRiskPolicySummary {
  readonly strategy?: string;
  readonly primary_filter?: string;
  readonly per_trade_fraction_pct?: number;
  readonly max_concurrent?: number;
  readonly max_deployed_fraction_pct?: number;
  readonly daily_loss_limit_pct?: number;
  readonly cost_bps?: number;
  readonly tp_pct?: number;
  readonly sl_pct?: number;
  readonly risk_unit_account_pct?: number;
}

export interface RlStrategyContext {
  readonly line?: 'rule_mainline' | 'rl_experiment' | 'evaluation' | 'unknown' | string;
  readonly label?: string;
  readonly primary_baseline?: string;
  readonly is_reinforcement_learning?: boolean;
  readonly is_environment_readiness?: boolean;
  readonly is_live_ready?: boolean;
  readonly is_profit_model?: boolean;
  readonly guardrail?: string;
  readonly readiness_status?: string | null;
  readonly risk_policy_summary?: RlRiskPolicySummary;
}

export interface RlRunRecord {
  readonly name: string;
  readonly artifact_type: RlArtifactType;
  readonly modified_at?: string;
  readonly summary?: JsonObject;
  readonly strategy_context?: RlStrategyContext;
  readonly policies?: readonly string[];
}

export interface RlRunDetail extends RlRunRecord {
  readonly artifacts?: readonly {
    readonly name: string;
    readonly suffix?: string;
    readonly size_bytes?: number;
    readonly modified_at?: string;
  }[];
  readonly detail?: JsonObject;
  readonly model?: {
    readonly model_type?: string;
    readonly feature_columns?: readonly string[];
    readonly train_summary?: JsonObject;
  };
}

export interface RlRunsResponse { readonly runs: readonly RlRunRecord[] }
export interface RlTableResponse {
  readonly run?: string;
  readonly artifact_type?: string;
  readonly table?: string;
  readonly policy?: string | null;
  readonly source_file?: string | null;
  readonly rows: readonly RlTableRow[];
  readonly row_count?: number;
  readonly truncated?: boolean;
  readonly policies?: readonly string[];
  readonly message?: string;
}
export interface RlCostGateResponse {
  readonly run?: string;
  readonly artifact_type?: string;
  readonly summary?: JsonObject;
  readonly gate?: RlTableResponse;
  readonly scenario?: RlTableResponse;
  readonly rolling?: RlTableResponse;
}
export interface RlProgressCriterion { readonly label: string; readonly passed: boolean; readonly evidence?: string }
export interface RlProgressPage {
  readonly page: string;
  readonly progress_pct: number;
  readonly status: 'complete' | 'in_progress' | string;
  readonly criteria?: readonly RlProgressCriterion[];
}
export interface RlProgressResponse {
  readonly mode?: string;
  readonly overall_progress_pct: number;
  readonly status: 'complete' | 'in_progress' | string;
  readonly pages: readonly RlProgressPage[];
  readonly evidence?: JsonObject;
}

export const rlApi = {
  rlRuns: (limit: number = 20) => fetchJson<RlRunsResponse>(`/api/rl/runs?limit=${limit}`),
  rlProgress: () => fetchJson<RlProgressResponse>('/api/rl/progress'),
  rlRun: (run: string) => fetchJson<RlRunDetail>(`/api/rl/runs/${encodeURIComponent(run)}`),
  rlActions: (run: string, limit: number = 500) => fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/actions?limit=${limit}`),
  rlTrades: (run: string, limit: number = 500) => fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/trades?limit=${limit}`),
  rlEquity: (run: string, limit: number = 500) => fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/equity?limit=${limit}`),
  rlEpisodes: (run: string, limit: number = 500) => fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/episodes?limit=${limit}`),
  rlEvents: (run: string, limit: number = 500) => fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/events?limit=${limit}`),
  rlTable: (run: string, table: string, limit: number = 500) =>
    fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/table/${encodeURIComponent(table)}?limit=${limit}`),
  rlWorkflowStages: (run: string, limit: number = 200) =>
    fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/table/stages?limit=${limit}`),
  rlWorkflowControls: (run: string, limit: number = 200) =>
    fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/table/controls?limit=${limit}`),
  rlProxyAvailability: (run: string, limit: number = 200) =>
    fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/table/proxy_availability?limit=${limit}`),
  rlOrderbookPersistence: (run: string, limit: number = 200) =>
    fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/table/orderbook_persistence?limit=${limit}`),
  rlParticipantStudyGroups: (run: string, limit: number = 200) =>
    fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/table/participant_study_groups?limit=${limit}`),
  rlFeatureAblation: (run: string, limit: number = 200) =>
    fetchJson<RlTableResponse>(`/api/rl/runs/${encodeURIComponent(run)}/table/feature_ablation?limit=${limit}`),
  rlCostGate: (run: string, limit: number = 500) => fetchJson<RlCostGateResponse>(`/api/rl/runs/${encodeURIComponent(run)}/cost-gate?limit=${limit}`),
};
