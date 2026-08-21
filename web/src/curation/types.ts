export type CandidateStatus = "pending" | "merged" | "rejected" | "deferred";
export type Confidence = "high" | "review";

export interface Candidate {
  candidate_id: string;
  confidence: Confidence;
  score: number;
  reasons: string[];
  warnings: string[];
  status: CandidateStatus;
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
}
