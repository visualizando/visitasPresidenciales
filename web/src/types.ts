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
  years?: number[];
  event_shard: string;
  score?: number;
  audiencias?: PersonAudiencias;
  audiencias_cr?: PersonAudienciasCr;
}

export interface PersonAudiencias {
  cargos: string[];
  instituciones: string[];
  audiencia_count?: number;
}

export interface PersonAudienciasCr {
  confirmed_count: number;
  likely_count: number;
  total_count: number;
  has_likely: boolean;
}

export type AudienciaStatus = "confirmed" | "likely" | "unconfirmed";

export interface AudienciaDetail {
  audiencia_id: string;
  entity_id: string;
  status: AudienciaStatus;
  official_name: string;
  official_cargo: string;
  lugar: string;
  date: string;
  cr_destination: string;
  cr_record_id: string;
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
  audiencia?: AudienciaDetail;
  fused_audiencias?: AudienciaDetail[];
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
  entity_id?: string;
  person_name?: string;
}

export interface MonthlyPoint {
  month: string;
  location: Location;
  records: number;
  people: number;
  entity_id?: string;
  person_name?: string;
}

export interface HeatmapPoint {
  location: Location;
  weekday: number;
  hour: number;
  records: number;
  entity_id?: string;
  person_name?: string;
}

export interface PurposePoint {
  location: Location;
  label: string;
  records: number;
  entity_id?: string;
  person_name?: string;
}

export interface ComparisonSeries {
  entityId: string;
  name: string;
  color: string;
}

export interface Analytics {
  daily: DailyPoint[];
  monthly: MonthlyPoint[];
  heatmap: HeatmapPoint[];
  purposes: PurposePoint[];
  current_presidency?: {start_date: string; heatmap: HeatmapPoint[]; purposes: PurposePoint[]};
  milei_casa_rosada_days?: string[];
  coverage: {first_date: string | null; last_date: string | null};
}

export interface ExportFile {
  year: number;
  records: number;
  path: string;
}

export interface RankingPeriod {
  id: string;
  label: string;
  start_date: string;
  end_date: string;
}

export interface RankingEntry {
  entity_id: string;
  canonical_name: string;
  document_type: string | null;
  document_number: string | null;
  daily_visits: number;
  first_visit: string;
  last_visit: string;
  casa_rosada: number;
  olivos: number;
}

export type RankingLocation = "all" | Location;
export type RankingGrouping = "presidency" | "year";
export interface RankingsData {
  version: number;
  definition: string;
  limit: number;
  years: RankingPeriod[];
  presidencies: RankingPeriod[];
  rankings: Record<RankingGrouping, Record<string, Record<RankingLocation, RankingEntry[]>>>;
}

export interface CoverageGap {
  start_month: string;
  end_month: string;
  reason: string;
}

export interface CoverageLocation {
  location: Location;
  months_with_data: number;
  gaps: CoverageGap[];
}

export interface CoverageFileIssue {
  path: string;
  location: Location;
  year: number;
  month: number;
  status: "active" | "missing" | "quarantined";
  parser: string | null;
  reason: string;
}

export interface CoverageData {
  version: number;
  first_date: string | null;
  last_date: string | null;
  older_period: {end_date: string; reason: string} | null;
  summary: {active_files: number; quarantined_files: number; missing_files: number; zero_record_files: number};
  locations: CoverageLocation[];
  file_issues: CoverageFileIssue[];
}

export type RawCoincidencePerson = [name: string, documentType: string | null, documentNumber: string | null];
export type RawCoincidenceEpisode = [personId: string, date: string, location: 0 | 1, destinationIndex: number, overlapMinutes: number, specificDestination: 0 | 1, overlapStart: string, overlapEnd: string];
export interface RawCoincidenceOwner { d: string[]; p: Record<string, RawCoincidencePerson>; e: RawCoincidenceEpisode[]; }
export type CoincidenceShard = Record<string, RawCoincidenceOwner>;

export interface CoincidenceEvidence {
  date: string;
  location: Location;
  destination: string;
  overlapMinutes: number;
  overlapStart: string;
  overlapEnd: string;
  specificDestination: boolean;
  ownerName: string;
}

export interface CoincidenceResult {
  entityId: string;
  canonicalName: string;
  documentType: string | null;
  documentNumber: string | null;
  days: number;
  episodes: number;
  overlapMinutes: number;
  specificEpisodes: number;
  latestDate: string;
  evidence: CoincidenceEvidence[];
}
