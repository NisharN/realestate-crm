export type Role = "owner" | "manager" | "agent";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  phone: string | null;
  rera_brn: string | null;
  languages: string[];
  areas: string[];
  external_ref: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Agency {
  id: string;
  name: string;
  slug: string;
  rera_orn: string | null;
  trade_license: string | null;
  emirate: string;
  phone: string | null;
  email: string | null;
  currency: string;
  timezone: string;
}

export interface Lead {
  id: string;
  name: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  email: string | null;
  nationality: string | null;
  language: string;
  source: string;
  external_id: string | null;
  campaign: string | null;
  listing_reference: string | null;
  purpose: string | null;
  property_type: string | null;
  bedrooms: number | null;
  areas: string[];
  budget_min_aed: number | null;
  budget_max_aed: number | null;
  timeline: string | null;
  stage: string;
  stage_changed_at: string | null;
  lost_reason: string | null;
  assigned_agent_id: string | null;
  assigned_agent: User | null;
  ai_broker_ref: string | null;
  payment_method: string | null;
  ai_score: number | null;
  ai_band: "hot" | "warm" | "cold" | null;
  ai_summary: string | null;
  ai_scored_at: string | null;
  consent_marketing: boolean;
  do_not_contact: boolean;
  last_contacted_at: string | null;
  next_follow_up_at: string | null;
  notes: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface Activity {
  id: string;
  lead_id: string | null;
  listing_id: string | null;
  kind: string;
  summary: string;
  data: Record<string, unknown>;
  actor_type: string;
  actor_id: string | null;
  created_at: string;
}

export interface Listing {
  id: string;
  reference: string;
  title: string;
  listing_type: "sale" | "rent";
  status: string;
  property_type: string;
  community: string;
  sub_community: string | null;
  building: string | null;
  emirate: string;
  bedrooms: number | null;
  bathrooms: number | null;
  size_sqft: number | null;
  price_aed: number;
  rent_frequency: string | null;
  completion_status: string;
  developer: string | null;
  permit_number: string | null;
  dld_number: string | null;
  description: string | null;
  amenities: string[];
  photos: string[];
  agent_id: string | null;
  portals: Record<string, unknown>;
  furnished: string | null;
  handover_date: string | null;
  latitude: number | null;
  longitude: number | null;
  last_verified_at: string | null;
  owner_name?: string | null;
  owner_phone?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Viewing {
  id: string;
  lead_id: string;
  listing_id: string | null;
  agent_id: string | null;
  lead?: Lead | null;
  listing?: Listing | null;
  scheduled_at: string | null;
  duration_min: number;
  status: string;
  location_note: string | null;
  feedback: string | null;
  external_id: string | null;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface Followup {
  id: string;
  lead_id: string;
  agent_id: string | null;
  lead?: Lead | null;
  overdue?: boolean;
  due_at: string;
  title: string;
  channel: string;
  note: string | null;
  status: string;
  done_at: string | null;
  external_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Deal {
  id: string;
  lead_id: string;
  listing_id: string | null;
  agent_id: string | null;
  deal_type: string;
  status: string;
  offer_aed: number | null;
  agreed_aed: number | null;
  commission_pct: number | null;
  commission_aed: number | null;
  mou_signed_at: string | null;
  transfer_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface Webhook {
  id: string;
  name: string;
  url: string;
  events: string[];
  active: boolean;
  last_delivery_at: string | null;
  last_status: number | null;
  failure_count: number;
  created_at: string;
  secret?: string;
}

export interface Delivery {
  id: string;
  event: string;
  status: string;
  attempts: number;
  response_status: number | null;
  error: string | null;
  next_attempt_at: string | null;
  created_at: string;
}

export interface Dashboard {
  stages: { stage: string; count: number }[];
  sources_30d: { source: string; count: number }[];
  bands: Record<string, number>;
  new_leads_7d: number;
  overdue_followups: number;
  viewings_next_7d: number;
  live_listings: number;
  closed_30d: number;
  commission_30d_aed: number;
}

export interface Today {
  followups: Followup[];
  viewings: Viewing[];
  hot_leads: Lead[];
  stale_leads: Lead[];
}

export interface LeadDetail {
  lead: Lead;
  activities: Activity[];
  viewings: Viewing[];
  followups: Followup[];
  deals: Deal[];
}

export interface Pipeline {
  columns: { stage: string; count: number; leads: Lead[] }[];
  total: number;
}

export interface Paged<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
