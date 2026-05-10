export type EvalSuite = {
  suite_id: string;
  name: string;
  description: string;
  target_graph_id: string;
  target_template_id: string;
  tags: string[];
  metadata: Record<string, unknown>;
  case_count: number;
  created_at: string;
  updated_at: string;
};

export type EvalCase = {
  suite_id: string;
  case_id: string;
  name: string;
  description: string;
  input_values: Record<string, unknown>;
  expected: Record<string, unknown>;
  checks: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type EvalCheckResult = {
  check_result_id?: string;
  result_id?: string;
  kind: string;
  name: string;
  status: string;
  score?: number | null;
  message: string;
  expected: Record<string, unknown>;
  actual: Record<string, unknown>;
  details: Record<string, unknown>;
  reviewer: string;
  created_at?: string;
};

export type EvalCaseResult = {
  result_id: string;
  eval_run_id: string;
  suite_id: string;
  case_id: string;
  case_name: string;
  graph_run_id: string;
  status: string;
  final_output: Record<string, unknown>;
  error: string;
  artifacts: Record<string, unknown>;
  node_failures: Array<Record<string, unknown>>;
  human_review: Record<string, unknown>;
  check_results: EvalCheckResult[];
  started_at: string;
  completed_at: string;
  created_at: string;
  updated_at: string;
};

export type EvalRun = {
  eval_run_id: string;
  suite_id: string;
  status: string;
  requested_by: string;
  metadata: Record<string, unknown>;
  started_at: string;
  completed_at: string;
  created_at: string;
  updated_at: string;
  case_results: EvalCaseResult[];
};

export type EvalBatchActionResult = {
  eval_run_id: string;
  results: EvalCaseResult[];
  started_count?: number;
  collected_count?: number;
  skipped_count: number;
  errors: Array<{
    case_id: string;
    message: string;
  }>;
};

export type EvalCollectOptions = {
  runLlmJudge?: boolean;
};
