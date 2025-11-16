export interface Highlight {
  start_time: string;
  end_time: string;
  description: string;
  commentary: string;
  audio_base64?: string;
}

export interface AnalyzeResponse {
  highlights: Highlight[];
  generated_video: string;
}

export interface AnalyzeRequest {
  filename: string;
}

export interface ApiError {
  error: string;
}

// Match Context types for RAG/Knowledge Base
export interface Player {
  jersey: string;
  name: string;
}

export interface Team {
  name: string;
  shirt_color?: string;
  players: Player[];
}

export interface MatchContext {
  teams: {
    home: Team;
    away: Team;
  };
}

export interface Event {
  time: string;
  description: string;
  replay: boolean;
  intensity: number;
}

export interface EventsData {
  events: Event[];
}

