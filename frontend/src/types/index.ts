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

