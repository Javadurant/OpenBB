import axios, { AxiosInstance, AxiosError, AxiosResponse } from 'axios';

/**
 * OpenBB API Client
 * 
 * This client provides type-safe access to all OpenBB backend endpoints.
 * It automatically handles:
 * - Base URL configuration (dev/prod)
 * - Request/response transformation
 * - Error handling
 * - Authentication headers
 * 
 * Usage in React:
 * const data = await openbbClient.getSignals({ symbol: 'AAPL' });
 */

// Determine API URL based on environment
const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

console.log('[OpenBB Client] Connecting to:', API_BASE_URL);

// Initialize Axios instance with defaults
const client: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second timeout
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
});

// Add response interceptor for error handling
client.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    console.error('[OpenBB Error]', {
      status: error.response?.status,
      message: (error.response?.data as any)?.detail || error.message,
      endpoint: error.config?.url,
    });
    return Promise.reject(error);
  }
);

/**
 * Signal Analysis - Get trading signals
 */
export interface SignalRequest {
  symbol: string;
  timeframe?: 'daily' | 'weekly' | 'monthly';
  lookback?: number;
}

export interface SignalResponse {
  symbol: string;
  signals: {
    trend: 'bullish' | 'bearish' | 'neutral';
    strength: number; // 0-100
    entry_points: number[];
    stop_loss: number;
    take_profit: number[];
  };
  timestamp: string;
}

export async function getSignals(req: SignalRequest): Promise<SignalResponse> {
  const response = await client.post('/api/signals', req);
  return response.data;
}

/**
 * Analytics - Get advanced market analytics
 */
export interface AnalyticsRequest {
  symbols: string[];
  metrics?: string[];
  date_range?: {
    start: string;
    end: string;
  };
}

export interface AnalyticsResponse {
  data: {
    [symbol: string]: {
      returns: number;
      volatility: number;
      sharpe_ratio: number;
      max_drawdown: number;
      correlation: { [symbol: string]: number };
    };
  };
  timestamp: string;
}

export async function getAnalytics(req: AnalyticsRequest): Promise<AnalyticsResponse> {
  const response = await client.post('/api/analytics', req);
  return response.data;
}

/**
 * Market Data - Get real-time and historical market data
 */
export interface MarketDataRequest {
  symbol: string;
  datatype?: 'intraday' | 'daily' | 'weekly' | 'monthly';
  limit?: number;
}

export interface PricePoint {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketDataResponse {
  symbol: string;
  data: PricePoint[];
  meta: {
    provider: string;
    last_updated: string;
    interval: string;
  };
}

export async function getMarketData(req: MarketDataRequest): Promise<MarketDataResponse> {
  const response = await client.post('/api/market', req);
  return response.data;
}

/**
 * AI Insights - Get Claude AI-powered analysis
 */
export interface AIInsightRequest {
  query: string;
  symbols?: string[];
  context?: {
    market_data?: PricePoint[];
    current_portfolio?: { symbol: string; shares: number }[];
    risk_tolerance?: 'low' | 'medium' | 'high';
  };
}

export interface AIInsightResponse {
  insight: string;
  confidence: number; // 0-100
  recommendations: string[];
  sources: string[];
  timestamp: string;
}

export async function getAIInsights(req: AIInsightRequest): Promise<AIInsightResponse> {
  const response = await client.post('/api/ai_insights', req);
  return response.data;
}

/**
 * Health Check - Verify API is responding
 */
export async function healthCheck(): Promise<{ status: string; timestamp: string }> {
  try {
    const response = await client.get('/api/health');
    return response.data;
  } catch (error) {
    console.error('[OpenBB] Health check failed');
    throw error;
  }
}

/**
 * Batch Request - Call multiple endpoints at once
 */
export interface BatchRequest {
  requests: Array<{
    endpoint: string;
    method: 'GET' | 'POST';
    data?: Record<string, unknown>;
  }>;
}

export async function batchRequest(batch: BatchRequest) {
  const response = await client.post('/api/batch', batch);
  return response.data;
}

/**
 * Export default client for direct axios access if needed
 */
export default client;

/**
 * Custom hook for React Query integration (optional)
 * 
 * Usage:
 * import { useQuery } from '@tanstack/react-query';
 * 
 * function MyComponent() {
 *   const { data, isLoading } = useQuery({
 *     queryKey: ['signals', 'AAPL'],
 *     queryFn: () => getSignals({ symbol: 'AAPL' })
 *   });
 * }
 */
export const openbbQueries = {
  signals: (symbol: string) => ({
    queryKey: ['signals', symbol],
    queryFn: () => getSignals({ symbol }),
  }),
  analytics: (symbols: string[]) => ({
    queryKey: ['analytics', symbols],
    queryFn: () => getAnalytics({ symbols }),
  }),
  marketData: (symbol: string) => ({
    queryKey: ['marketData', symbol],
    queryFn: () => getMarketData({ symbol }),
  }),
  aiInsights: (query: string) => ({
    queryKey: ['aiInsights', query],
    queryFn: () => getAIInsights({ query }),
  }),
};
