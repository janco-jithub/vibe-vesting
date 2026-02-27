// API Client for the trading dashboard

const API_BASE = 'http://localhost:8000/api';

async function fetchApi<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export const api = {
  // Account
  getAccount: () => fetchApi<import('./types').AccountStatus>('/account'),

  // Positions
  getPositions: () => fetchApi<import('./types').Position[]>('/positions'),

  // Signal
  getSignal: () => fetchApi<import('./types').Signal | { signal: null; message: string }>('/signal'),

  // All signals from all strategies
  getAllSignals: () =>
    fetchApi<{ signals: import('./types').AllSignal[]; count: number }>('/signals/all'),

  // Trades
  getTrades: (limit = 50) => fetchApi<import('./types').Trade[]>(`/trades?limit=${limit}`),

  // Equity curve
  getEquityCurve: () => fetchApi<{ data: import('./types').EquityPoint[] }>('/equity-curve'),

  // Market data
  getMarketData: (symbol: string, days = 30) =>
    fetchApi<import('./types').MarketData>(`/market-data/${symbol}?days=${days}`),

  // Backtest
  runBacktest: (startDate: string, endDate: string, capital = 10000) =>
    fetchApi<import('./types').BacktestResult>(
      `/backtest?start_date=${startDate}&end_date=${endDate}&initial_capital=${capital}`
    ),

  // Risk status
  getRiskStatus: () => fetchApi<import('./types').RiskStatus>('/risk-status'),

  // Strategy performance
  getStrategyPerformance: () =>
    fetchApi<{ strategies: import('./types').StrategyPerformance[] }>('/strategy-performance'),

  // Market status
  getMarketStatus: () => fetchApi<import('./types').MarketStatus>('/market-status'),

  // Health check
  getHealth: () => fetchApi<{ status: string; timestamp: string }>('/health'),

  // Pairs trading status
  getPairsStatus: () =>
    fetchApi<{ pairs: import('./types').PairStatus[]; count: number }>('/pairs-status'),

  // Bot insights - what the bot is thinking and doing
  getBotInsights: () => fetchApi<import('./types').BotInsights>('/bot-insights'),

  // Daily Journal
  getJournal: (limit = 30) => fetchApi<import('./types').DailyJournalEntry[]>(`/journal?limit=${limit}`),

  getJournalSummary: () => fetchApi<import('./types').JournalSummary>('/journal/summary'),

  createJournalEntry: async (entry: {
    date: string;
    starting_equity: number;
    ending_equity: number;
    notes?: string;
  }) => {
    const response = await fetch(`${API_BASE}/journal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry),
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<import('./types').DailyJournalEntry>;
  },

  deleteJournalEntry: async (date: string) => {
    const response = await fetch(`${API_BASE}/journal/${date}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return response.json();
  },
};
