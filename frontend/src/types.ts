// API Response Types

export interface AccountStatus {
  equity: number;
  cash: number;
  buying_power: number;
  portfolio_value: number;
  daily_pnl: number;
  daily_return: number;
  total_return: number;
  status: string;
}

export interface Position {
  symbol: string;
  quantity: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  current_price: number;
  avg_entry_price: number;
}

export interface Signal {
  date: string;
  symbol: string;
  signal_type: string;
  strength: number;
  momentum_scores?: MomentumScore[];
}

export interface MomentumScore {
  symbol: string;
  return_12m: number;
  rank: number;
}

export interface Trade {
  id: number;
  timestamp: string;
  symbol: string;
  action: string;
  quantity: number;
  price: number;
  value: number;
}

export interface BacktestResult {
  strategy: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_equity: number;
  total_return: number;
  cagr: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  win_rate: number;
  trade_count: number;
  equity_curve: EquityPoint[];
}

export interface EquityPoint {
  date: string;
  equity: number;
}

export interface RiskStatus {
  can_trade: boolean;
  halt_reason: string | null;
  daily_return: string;
  daily_limit: string;
  weekly_return: string;
  weekly_limit: string;
  drawdown: string;
  drawdown_limit: string;
}

export interface MarketData {
  symbol: string;
  data: OHLCV[];
}

export interface OHLCV {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StrategyPerformance {
  name: string;
  description?: string;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  trade_count: number;
  rebalance_frequency?: string;
  status: string;
}

export interface AllSignal {
  strategy: string;
  date: string;
  symbol: string;
  signal_type: string;
  strength: number;
  description: string;
  metadata?: Record<string, unknown>;
}

export interface MarketStatus {
  is_open: boolean;
  next_open: string | null;
  next_close: string | null;
}

export interface PairStatus {
  pair: string;
  status: string;
  z_score?: number;
  correlation?: number;
  hedge_ratio?: number;
  is_cointegrated?: boolean;
  reason?: string;
}

export interface BotInsights {
  timestamp: string;
  account: {
    equity: number;
    cash: number;
    buying_power: number;
    position_count: number;
  };
  market_phase: string;
  positions: BotPosition[];
  pending_actions: PendingAction[];
  new_position_candidates: PositionCandidate[];
  active_signals: {
    simple_momentum: BotSignal[];
    pairs_trading: BotSignal[];
  };
  summary: {
    total_positions: number;
    profitable_positions: number;
    losing_positions: number;
    pending_action_count: number;
    new_candidates: number;
  };
}

export interface BotPosition {
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  pnl_pct: number;
  pnl_dollars: number;
  market_value: number;
  strategy: string;
  stop_loss: number;
  highest_price: number;
  stop_distance_pct: number;
}

export interface PendingAction {
  symbol: string;
  actions: {
    action: string;
    description: string;
    priority: string;
    target_qty?: number;
    new_stop?: number;
  }[];
}

export interface PositionCandidate {
  symbol: string;
  strategy: string;
  strength: number;
  momentum: number;
  reason: string;
}

export interface BotSignal {
  symbol: string;
  action: string;
  strength: number;
  momentum?: number;
  in_position: boolean;
  strategy: string;
}

// Daily Journal types
export interface DailyJournalEntry {
  id: number;
  date: string;
  starting_equity: number;
  ending_equity: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  notes?: string;
}

export interface JournalSummary {
  total_entries: number;
  total_pnl: number;
  total_pnl_pct: number;
  winning_days: number;
  losing_days: number;
  win_rate: number;
  best_day: { date: string; pnl: number; pct: number } | null;
  worst_day: { date: string; pnl: number; pct: number } | null;
  average_daily_pnl: number;
  average_daily_pct: number;
  current_streak: number;
}
