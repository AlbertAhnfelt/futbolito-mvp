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
  language?: string;
  use_graph_llm?: boolean;
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

// Streaming API types
export interface StreamStatusEvent {
  type: 'status';
  message: string;
  progress: number;
}

export interface StreamChunkReadyEvent {
  type: 'chunk_ready';
  index: number;
  url: string;
  start_time: string;
  end_time: string;
  progress: number;
}

export interface StreamCompleteEvent {
  type: 'complete';
  chunks: number;
  final_video: string;
  progress: number;
}

export interface StreamErrorEvent {
  type: 'error';
  message: string;
}

export type StreamEvent =
  | StreamStatusEvent
  | StreamChunkReadyEvent
  | StreamCompleteEvent
  | StreamErrorEvent;

export interface VideoChunk {
  index: number;
  url: string;
  startTime: string;
  endTime: string;
}

