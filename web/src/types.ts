export type Location = "casa-rosada" | "olivos";
export type RecordType = "movement" | "person" | "vehicle" | "visitor";

export interface Meta {
  version: number;
  generated_at: string;
  record_count: number;
  people_count: number;
  source_count: number;
  first_date: string | null;
  last_date: string | null;
  locations: Location[];
  is_demo: boolean;
}

export interface PersonSummary {
  entity_id: string;
  canonical_name: string;
  normalized_name: string;
  document_type: string | null;
  document_number: string | null;
  record_count: number;
  first_seen: string | null;
  last_seen: string | null;
  locations: Location[];
  record_types: RecordType[];
  event_shard: string;
  score?: number;
}

export interface SourceLink {
  url: string;
  path: string;
  page: number;
}

export interface AccessEvent {
  record_id: string;
  entity_id: string;
  canonical_name: string;
  document_type: string | null;
  document_number: string | null;
  location: Location;
  record_type: RecordType;
  occurred_at: string | null;
  entered_at: string | null;
  exited_at: string | null;
  direction: string | null;
  device: string | null;
  destination: string | null;
  purpose: string | null;
  activity: string | null;
  authorized_by: string | null;
  access_status: string | null;
  quality: "high" | "medium" | "low";
  raw_text: string;
  sources: SourceLink[];
}

export interface SearchFilters {
  location: "all" | Location;
  year: "all" | number;
  recordType: "all" | RecordType;
}

export interface DailyPoint {
  date: string;
  location: Location;
  record_type: RecordType;
  records: number;
  people: number;
}

export interface MonthlyPoint {
  month: string;
  location: Location;
  records: number;
  people: number;
}

export interface HeatmapPoint {
  location: Location;
  weekday: number;
  hour: number;
  records: number;
}

export interface PurposePoint {
  location: Location;
  label: string;
  records: number;
}

export interface Analytics {
  daily: DailyPoint[];
  monthly: MonthlyPoint[];
  heatmap: HeatmapPoint[];
  purposes: PurposePoint[];
  coverage: {first_date: string | null; last_date: string | null};
}

export interface ExportFile {
  year: number;
  records: number;
  path: string;
}
