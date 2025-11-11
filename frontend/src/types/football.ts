/**
 * TypeScript types for FBRApi football data.
 * These match the Pydantic models in the backend.
 */

export interface RosterPlayer {
  id: string;
  name: string;
  jersey_number?: string;
  position?: string;
  age?: number;
  nationality?: string;
}

export interface TeamSearchResult {
  id: string;
  name: string;
  country?: string;
  league?: string;
  logo_url?: string;
}

export interface TeamDetails {
  id: string;
  name: string;
  country?: string;
  league?: string;
  founded?: number;
  stadium?: string;
  logo_url?: string;
  roster: RosterPlayer[];
}

export interface GameSearchResult {
  id: string;
  home_team: string;
  away_team: string;
  home_team_id: string;
  away_team_id: string;
  date: string;
  competition?: string;
  status?: string;
}

export interface GameDetails {
  id: string;
  home_team: TeamSearchResult;
  away_team: TeamSearchResult;
  date: string;
  competition?: string;
  venue?: string;
  status?: string;
  home_score?: number;
  away_score?: number;
  home_lineup: RosterPlayer[];
  away_lineup: RosterPlayer[];
}

export interface GameFilters {
  team_id?: string;
  team_name?: string;
  date_from?: string;
  date_to?: string;
  competition?: string;
}
