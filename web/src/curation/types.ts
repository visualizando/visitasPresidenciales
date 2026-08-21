export type CandidateStatus = "pending" | "merged" | "rejected" | "deferred";
export type Confidence = "high" | "review";
export type ActivityLevel = "very_high" | "high" | "medium" | "low";

export interface Candidate {
  candidate_id: string;
  confidence: Confidence;
  score: number;
  reasons: string[];
  warnings: string[];
  status: CandidateStatus;
  activity_level: ActivityLevel;
  total_records: number;
  batch_id: string | null;
  recommended_canonical_id: string;
  left_entity_id: string;
  left_name: string;
  left_document: string;
  left_records: number;
  left_first_seen: string;
  left_last_seen: string;
  left_locations: string;
  right_entity_id: string;
  right_name: string;
  right_document: string;
  right_records: number;
  right_first_seen: string;
  right_last_seen: string;
  right_locations: string;
}

export interface BatchInfo {
  batch_id: string;
  status: "applied" | "undone";
  created_at: string;
  merge_count: number;
  component_count: number;
}

export interface BatchPreview {
  rule: string;
  candidate_edges: number;
  eligible_components: number;
  eligible_identities: number;
  merge_operations: number;
  excluded_no_document_components: number;
  excluded_no_document_merges: number;
  excluded_conflict_components: number;
  excluded_conflict_merges: number;
  excluded_curated_components: number;
  excluded_curated_merges: number;
  latest_batch: BatchInfo | null;
  batch?: BatchInfo;
}

export interface Summary {
  total: number;
  pending: number;
  merged: number;
  rejected: number;
  deferred: number;
  high: number;
  review: number;
}

export interface CandidatePage {
  items: Candidate[];
  offset: number;
  limit: number;
  total: number;
  summary: Summary;
  activity_summary: Record<ActivityLevel | "all", number>;
}
