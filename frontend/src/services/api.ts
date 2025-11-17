import axios from 'axios';
import type { AnalyzeResponse, AnalyzeRequest, MatchContext, EventsData } from '../types';

// Configure API base URL - update this for production
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const videoApi = {
  /**
   * Get list of available videos
   */
  listVideos: async (): Promise<string[]> => {
    const response = await apiClient.get<string[]>('/videos/list');
    return response.data;
  },

  /**
   * Analyze a video and get highlights with generated commentary video (BATCH MODE - deprecated)
   */
  analyzeVideo: async (
    filename: string,
    language: string,              // ✅ changed: add language parameter
  ): Promise<AnalyzeResponse> => {
    const payload: AnalyzeRequest = {
      filename,
      language,                   // ✅ changed: include language in request body
    };
    const response = await apiClient.post<AnalyzeResponse>('/analyze', payload);
    return response.data;
  },

  /**
   * Analyze a video with real-time streaming (STREAMING MODE - recommended)
   * Returns an EventSource for Server-Sent Events
   */
  analyzeVideoStream: (filename: string): EventSource => {
    const url = `${API_BASE_URL}/analyze-stream/${encodeURIComponent(filename)}`;
    return new EventSource(url);
  },

  /**
   * Get detected events from events.json
   */
  getEvents: async (): Promise<EventsData> => {
    const response = await apiClient.get<EventsData>('/events');
    return response.data;
  },
};

export const matchContextApi = {
  /**
   * Save match context (team names, player info)
   */
  saveContext: async (context: MatchContext): Promise<void> => {
    await apiClient.post('/match-context', context);
  },

  /**
   * Get current match context
   */
  getContext: async (): Promise<MatchContext | null> => {
    const response = await apiClient.get<MatchContext | null>('/match-context');
    return response.data;
  },

  /**
   * Clear match context
   */
  clearContext: async (): Promise<void> => {
    await apiClient.delete('/match-context');
  },
};

export default apiClient;
