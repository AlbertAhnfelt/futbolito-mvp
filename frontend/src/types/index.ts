export interface Highlight {
  start_time: string;
  end_time: string;
  description: string;
}

export interface AnalyzeRequest {
  filename: string;
}

export interface ApiError {
  error: string;
}

