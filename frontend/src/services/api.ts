import axios from 'axios';
import type { AnalyzeResponse, AnalyzeRequest, MatchContext } from '../types';
import type {
  TeamSearchResult,
  TeamDetails,
  GameSearchResult,
  GameDetails,
  GameFilters,
  RosterPlayer,
} from '../types/football';

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
   * Analyze a video and get highlights with generated commentary video
   */
  analyzeVideo: async (filename: string): Promise<AnalyzeResponse> => {
    const payload: AnalyzeRequest = { filename };
    const response = await apiClient.post<AnalyzeResponse>('/analyze', payload);
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

export const footballApi = {
  /**
   * Search for teams by name
   */
  searchTeams: async (query: string): Promise<TeamSearchResult[]> => {
    const response = await apiClient.get<TeamSearchResult[]>('/teams/search', {
      params: { query },
    });
    return response.data;
  },

  /**
   * Get detailed team information
   */
  getTeam: async (teamId: string): Promise<TeamDetails> => {
    const response = await apiClient.get<TeamDetails>(`/teams/${teamId}`);
    return response.data;
  },

  /**
   * Search for games based on filters
   */
  searchGames: async (filters: GameFilters): Promise<GameSearchResult[]> => {
    const response = await apiClient.get<GameSearchResult[]>('/games/search', {
      params: filters,
    });
    return response.data;
  },

  /**
   * Get detailed game information including lineups
   */
  getGame: async (gameId: string): Promise<GameDetails> => {
    const response = await apiClient.get<GameDetails>(`/games/${gameId}`);
    return response.data;
  },

  /**
   * Get roster for a specific team
   */
  getRoster: async (teamId: string): Promise<RosterPlayer[]> => {
    const response = await apiClient.get<RosterPlayer[]>(`/rosters/${teamId}`);
    return response.data;
  },

  /**
   * Clear API cache
   */
  clearCache: async (cacheType?: 'teams' | 'games' | 'rosters'): Promise<void> => {
    const params = cacheType ? { cache_type: cacheType } : {};
    await apiClient.delete('/cache', { params });
  },
};

export default apiClient;

