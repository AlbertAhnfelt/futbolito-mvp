import axios from 'axios';
import type { Highlight, AnalyzeRequest } from '../types';

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
   * Analyze a video and get highlights
   */
  analyzeVideo: async (filename: string): Promise<Highlight[]> => {
    const payload: AnalyzeRequest = { filename };
    const response = await apiClient.post<Highlight[]>('/analyze', payload);
    return response.data;
  },
};

export default apiClient;

