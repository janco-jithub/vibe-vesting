import { useEffect, useState } from 'react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area
} from 'recharts';
import {
  TrendingUp, DollarSign, Activity, AlertTriangle,
  CheckCircle, XCircle, RefreshCw, HelpCircle, Play, Pause, Eye,
  Zap, Brain, GitCompare, BarChart3, Flame, BookOpen, Plus, Trash2, Calendar
} from 'lucide-react';
import { api } from '../api';
import type {
  AccountStatus, Position, Signal, Trade, BacktestResult,
  RiskStatus, StrategyPerformance, MarketStatus, OHLCV, AllSignal, PairStatus,
  BotInsights, DailyJournalEntry, JournalSummary
} from '../types';

// Format currency
const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);

// Format percentage
const formatPercent = (value: number) =>
  `${(value * 100).toFixed(2)}%`;

// ETF and Stock descriptions
const ETF_INFO: Record<string, { name: string; description: string }> = {
  // ETFs
  SPY: { name: 'S&P 500', description: 'Top 500 US companies' },
  QQQ: { name: 'Nasdaq 100', description: 'Top tech companies' },
  TLT: { name: 'Treasury Bonds', description: 'Safe haven - US govt bonds' },
  IWM: { name: 'Russell 2000', description: 'Small cap US stocks' },
  XLF: { name: 'Financials', description: 'Banks & financial services' },
  XLK: { name: 'Technology', description: 'Tech sector ETF' },
  XLE: { name: 'Energy', description: 'Oil, gas & energy' },
  XLV: { name: 'Healthcare', description: 'Pharma & healthcare' },
  XLI: { name: 'Industrials', description: 'Manufacturing & industrials' },
  XLU: { name: 'Utilities', description: 'Electric & gas utilities' },
  XLC: { name: 'Communications', description: 'Media & telecom' },
  // High-volatility tech stocks
  NVDA: { name: 'NVIDIA', description: 'AI & GPU leader' },
  TSLA: { name: 'Tesla', description: 'EV & clean energy' },
  AMD: { name: 'AMD', description: 'Semiconductors' },
  META: { name: 'Meta', description: 'Social media & VR' },
  MSTR: { name: 'MicroStrategy', description: 'Bitcoin proxy' },
  SMCI: { name: 'Super Micro', description: 'AI server hardware' },
  COIN: { name: 'Coinbase', description: 'Crypto exchange' },
  PLTR: { name: 'Palantir', description: 'AI & data analytics' },
  SHOP: { name: 'Shopify', description: 'E-commerce platform' },
  SQ: { name: 'Block/Square', description: 'Fintech payments' },
  ROKU: { name: 'Roku', description: 'Streaming platform' },
  UPST: { name: 'Upstart', description: 'AI lending' },
  HOOD: { name: 'Robinhood', description: 'Trading platform' },
  RIOT: { name: 'Riot Platforms', description: 'Bitcoin mining' },
  MARA: { name: 'Marathon Digital', description: 'Bitcoin mining' },
};

// Strategy colors
const STRATEGY_COLORS: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  'Dual Momentum': { bg: 'bg-blue-50', border: 'border-blue-300', text: 'text-blue-700', icon: 'text-blue-500' },
  'Swing Momentum': { bg: 'bg-green-50', border: 'border-green-300', text: 'text-green-700', icon: 'text-green-500' },
  'Simple Momentum': { bg: 'bg-teal-50', border: 'border-teal-300', text: 'text-teal-700', icon: 'text-teal-500' },
  'ML Momentum': { bg: 'bg-purple-50', border: 'border-purple-300', text: 'text-purple-700', icon: 'text-purple-500' },
  'Pairs Trading': { bg: 'bg-orange-50', border: 'border-orange-300', text: 'text-orange-700', icon: 'text-orange-500' },
  'Volatility Breakout': { bg: 'bg-red-50', border: 'border-red-300', text: 'text-red-700', icon: 'text-red-500' },
  'Unknown': { bg: 'bg-gray-50', border: 'border-gray-300', text: 'text-gray-600', icon: 'text-gray-500' },
};

// Help tooltip component
const HelpTip = ({ text }: { text: string }) => (
  <div className="group relative inline-block ml-1">
    <HelpCircle className="w-4 h-4 text-gray-400 cursor-help inline" />
    <div className="invisible group-hover:visible absolute z-50 w-64 p-3 bg-gray-900 text-white text-sm rounded-lg -top-2 left-6 shadow-lg">
      {text}
      <div className="absolute w-2 h-2 bg-gray-900 transform rotate-45 -left-1 top-3"></div>
    </div>
  </div>
);

// Card component
const Card = ({ title, help, children, className = '', badge }: {
  title: string;
  help?: string;
  children: React.ReactNode;
  className?: string;
  badge?: React.ReactNode;
}) => (
  <div className={`bg-white rounded-xl shadow-sm border border-gray-200 p-5 ${className}`}>
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-sm font-semibold text-gray-700 flex items-center">
        {title}
        {help && <HelpTip text={help} />}
      </h3>
      {badge}
    </div>
    {children}
  </div>
);

// Strategy icon component
const StrategyIcon = ({ strategy }: { strategy: string }) => {
  const colors = STRATEGY_COLORS[strategy] || STRATEGY_COLORS['Dual Momentum'];
  switch (strategy) {
    case 'Dual Momentum':
      return <TrendingUp className={`w-4 h-4 ${colors.icon}`} />;
    case 'Swing Momentum':
      return <Zap className={`w-4 h-4 ${colors.icon}`} />;
    case 'Simple Momentum':
      return <TrendingUp className={`w-4 h-4 ${colors.icon}`} />;
    case 'ML Momentum':
      return <Brain className={`w-4 h-4 ${colors.icon}`} />;
    case 'Pairs Trading':
      return <GitCompare className={`w-4 h-4 ${colors.icon}`} />;
    case 'Volatility Breakout':
      return <Flame className={`w-4 h-4 ${colors.icon}`} />;
    default:
      return <Activity className={`w-4 h-4 ${colors.icon}`} />;
  }
};

export default function Dashboard() {
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [, setSignal] = useState<Signal | null>(null);
  const [allSignals, setAllSignals] = useState<AllSignal[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [, setBacktest] = useState<BacktestResult | null>(null);
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [strategies, setStrategies] = useState<StrategyPerformance[]>([]);
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [marketData, setMarketData] = useState<OHLCV[]>([]);
  const [pairsStatus, setPairsStatus] = useState<PairStatus[]>([]);
  const [botInsights, setBotInsights] = useState<BotInsights | null>(null);
  const [journalEntries, setJournalEntries] = useState<DailyJournalEntry[]>([]);
  const [journalSummary, setJournalSummary] = useState<JournalSummary | null>(null);
  const [showJournalForm, setShowJournalForm] = useState(false);
  const [journalForm, setJournalForm] = useState({
    date: new Date().toISOString().split('T')[0],
    starting_equity: '',
    ending_equity: '',
    notes: ''
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [
        accountData,
        positionsData,
        signalData,
        allSignalsData,
        tradesData,
        riskData,
        strategyData,
        marketStatusData,
        spyData,
        pairsData,
        botInsightsData,
        journalData,
        journalSummaryData,
      ] = await Promise.all([
        api.getAccount(),
        api.getPositions(),
        api.getSignal(),
        api.getAllSignals(),
        api.getTrades(20),
        api.getRiskStatus(),
        api.getStrategyPerformance(),
        api.getMarketStatus(),
        api.getMarketData('SPY', 90),
        api.getPairsStatus().catch(() => ({ pairs: [], count: 0 })),
        api.getBotInsights().catch(() => null),
        api.getJournal(30).catch(() => []),
        api.getJournalSummary().catch(() => null),
      ]);

      setAccount(accountData);
      setPositions(positionsData);
      setSignal('signal_type' in signalData ? signalData as Signal : null);
      setAllSignals(allSignalsData.signals || []);
      setTrades(tradesData);
      setRiskStatus(riskData);
      setStrategies(strategyData.strategies || []);
      setMarketStatus(marketStatusData);
      setMarketData(spyData.data || []);
      setPairsStatus(pairsData.pairs || []);
      setBotInsights(botInsightsData);
      setJournalEntries(journalData || []);
      setJournalSummary(journalSummaryData);
      setLastUpdate(new Date());

      // Also fetch backtest
      try {
        const backtestData = await api.runBacktest('2024-01-01', '2025-12-31', 10000);
        setBacktest(backtestData);
      } catch {
        // Backtest might fail if not enough data
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  // Journal form handlers
  const handleJournalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createJournalEntry({
        date: journalForm.date,
        starting_equity: parseFloat(journalForm.starting_equity),
        ending_equity: parseFloat(journalForm.ending_equity),
        notes: journalForm.notes || undefined
      });
      // Refresh journal data
      const [newJournal, newSummary] = await Promise.all([
        api.getJournal(30),
        api.getJournalSummary()
      ]);
      setJournalEntries(newJournal);
      setJournalSummary(newSummary);
      setShowJournalForm(false);
      setJournalForm({
        date: new Date().toISOString().split('T')[0],
        starting_equity: '',
        ending_equity: '',
        notes: ''
      });
    } catch (err) {
      console.error('Failed to save journal entry:', err);
    }
  };

  const handleDeleteJournal = async (date: string) => {
    if (!confirm(`Delete journal entry for ${date}?`)) return;
    try {
      await api.deleteJournalEntry(date);
      const [newJournal, newSummary] = await Promise.all([
        api.getJournal(30),
        api.getJournalSummary()
      ]);
      setJournalEntries(newJournal);
      setJournalSummary(newSummary);
    } catch (err) {
      console.error('Failed to delete journal entry:', err);
    }
  };

  // Count signals by strategy
  const signalsByStrategy = allSignals.reduce((acc, sig) => {
    acc[sig.strategy] = (acc[sig.strategy] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  // Determine system status
  const getSystemStatus = () => {
    if (error) return { status: 'error', message: 'Connection problem - cannot reach the trading system' };
    if (loading && !account) return { status: 'loading', message: 'Starting up...' };
    if (!riskStatus?.can_trade) return { status: 'halted', message: 'Trading paused - safety limits triggered' };
    if (!marketStatus?.is_open) return { status: 'waiting', message: 'Waiting for market to open' };
    if (positions.length > 0) return { status: 'holding', message: `Holding ${positions.length} position${positions.length > 1 ? 's' : ''}` };
    return { status: 'ready', message: 'Ready to trade when conditions are right' };
  };

  const systemStatus = getSystemStatus();

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <div className="bg-white p-8 rounded-2xl shadow-lg border border-red-200 max-w-md w-full">
          <div className="flex items-center gap-3 text-red-600 mb-4">
            <AlertTriangle className="w-8 h-8" />
            <h2 className="text-xl font-bold">Can't Connect</h2>
          </div>
          <p className="text-gray-600 mb-4">
            The trading system isn't responding. Make sure the backend server is running.
          </p>
          <div className="bg-gray-50 rounded-lg p-4 mb-4">
            <p className="text-sm text-gray-500 mb-2">To start everything, run:</p>
            <code className="text-sm bg-gray-200 px-2 py-1 rounded block">
              ./scripts/start_trading.sh
            </code>
          </div>
          <button
            onClick={fetchData}
            className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center justify-center gap-2 font-medium"
          >
            <RefreshCw className="w-4 h-4" />
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 shadow-sm sticky top-0 z-40">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <BarChart3 className="w-7 h-7 text-blue-600" />
              Trading Bot Dashboard
            </h1>
            <p className="text-sm text-gray-500">5 strategies running automatically</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-2xl font-bold text-gray-900">
                {account ? formatCurrency(account.equity) : '...'}
              </p>
              {account && (
                <p className={`text-sm font-medium ${account.total_return >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {account.total_return >= 0 ? '↑' : '↓'} {formatPercent(Math.abs(account.total_return))}
                </p>
              )}
            </div>
            <div className="border-l border-gray-200 pl-4 flex items-center gap-2">
              <span className="text-xs text-gray-400">
                {lastUpdate.toLocaleTimeString()}
              </span>
              <button
                onClick={fetchData}
                disabled={loading}
                className="p-2 hover:bg-gray-100 rounded-lg disabled:opacity-50 transition-colors"
                title="Refresh"
              >
                <RefreshCw className={`w-5 h-5 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-6">
        {/* Status Banner */}
        <div className={`rounded-2xl p-5 mb-6 ${
          systemStatus.status === 'error' ? 'bg-red-50 border-2 border-red-200' :
          systemStatus.status === 'halted' ? 'bg-yellow-50 border-2 border-yellow-200' :
          systemStatus.status === 'holding' ? 'bg-green-50 border-2 border-green-200' :
          'bg-blue-50 border-2 border-blue-200'
        }`}>
          <div className="flex items-center gap-4">
            <div className={`p-3 rounded-full ${
              systemStatus.status === 'error' ? 'bg-red-100' :
              systemStatus.status === 'halted' ? 'bg-yellow-100' :
              systemStatus.status === 'holding' ? 'bg-green-100' :
              'bg-blue-100'
            }`}>
              {systemStatus.status === 'error' ? <XCircle className="w-6 h-6 text-red-600" /> :
               systemStatus.status === 'halted' ? <Pause className="w-6 h-6 text-yellow-600" /> :
               systemStatus.status === 'holding' ? <Play className="w-6 h-6 text-green-600" /> :
               systemStatus.status === 'waiting' ? <Eye className="w-6 h-6 text-blue-600" /> :
               <Activity className="w-6 h-6 text-blue-600" />}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <h2 className="text-lg font-bold text-gray-900">{systemStatus.message}</h2>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  marketStatus?.is_open ? 'bg-green-200 text-green-800' : 'bg-gray-200 text-gray-600'
                }`}>
                  Market {marketStatus?.is_open ? 'Open' : 'Closed'}
                </span>
              </div>
              <div className="flex items-center gap-4 mt-2 text-sm text-gray-600">
                <span className="flex items-center gap-1">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  {allSignals.length} active signals
                </span>
                <span className="flex items-center gap-1">
                  {riskStatus?.can_trade ?
                    <CheckCircle className="w-4 h-4 text-green-500" /> :
                    <XCircle className="w-4 h-4 text-red-500" />}
                  Safety: {riskStatus?.can_trade ? 'OK' : 'Halted'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 5 Strategies Explanation */}
        <Card title="5 Active Trading Strategies" className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
            {/* Dual Momentum */}
            <div className="bg-blue-50 rounded-lg p-3 border-l-4 border-blue-500">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-4 h-4 text-blue-600" />
                <span className="font-semibold text-gray-900 text-sm">Dual Momentum</span>
              </div>
              <p className="text-xs text-gray-600 mb-2">
                Monthly rebalance. Buys strongest of SPY/QQQ or bonds if both down.
              </p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-blue-600 font-medium">Monthly</span>
                {signalsByStrategy['Dual Momentum'] && (
                  <span className="px-2 py-0.5 bg-blue-200 text-blue-800 rounded text-xs">
                    {signalsByStrategy['Dual Momentum']}
                  </span>
                )}
              </div>
            </div>

            {/* Swing Momentum */}
            <div className="bg-green-50 rounded-lg p-3 border-l-4 border-green-500">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="w-4 h-4 text-green-600" />
                <span className="font-semibold text-gray-900 text-sm">Swing Momentum</span>
              </div>
              <p className="text-xs text-gray-600 mb-2">
                Daily RSI & MA signals across 8 sector ETFs for active trading.
              </p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-green-600 font-medium">Daily</span>
                {signalsByStrategy['Swing Momentum'] && (
                  <span className="px-2 py-0.5 bg-green-200 text-green-800 rounded text-xs">
                    {signalsByStrategy['Swing Momentum']}
                  </span>
                )}
              </div>
            </div>

            {/* ML Momentum */}
            <div className="bg-purple-50 rounded-lg p-3 border-l-4 border-purple-500">
              <div className="flex items-center gap-2 mb-2">
                <Brain className="w-4 h-4 text-purple-600" />
                <span className="font-semibold text-gray-900 text-sm">ML Momentum</span>
              </div>
              <p className="text-xs text-gray-600 mb-2">
                LightGBM predicts returns using 20+ technical features.
              </p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-purple-600 font-medium">Daily</span>
                {signalsByStrategy['ML Momentum'] && (
                  <span className="px-2 py-0.5 bg-purple-200 text-purple-800 rounded text-xs">
                    {signalsByStrategy['ML Momentum']}
                  </span>
                )}
              </div>
            </div>

            {/* Pairs Trading */}
            <div className="bg-orange-50 rounded-lg p-3 border-l-4 border-orange-500">
              <div className="flex items-center gap-2 mb-2">
                <GitCompare className="w-4 h-4 text-orange-600" />
                <span className="font-semibold text-gray-900 text-sm">Pairs Trading</span>
              </div>
              <p className="text-xs text-gray-600 mb-2">
                Statistical arbitrage on correlated ETF pairs. Market neutral.
              </p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-orange-600 font-medium">Daily</span>
                {signalsByStrategy['Pairs Trading'] ? (
                  <span className="px-2 py-0.5 bg-orange-200 text-orange-800 rounded text-xs">
                    {signalsByStrategy['Pairs Trading']}
                  </span>
                ) : (
                  <span className="px-2 py-0.5 bg-gray-200 text-gray-600 rounded text-xs">
                    Watching
                  </span>
                )}
              </div>
            </div>

            {/* Volatility Breakout */}
            <div className="bg-red-50 rounded-lg p-3 border-l-4 border-red-500">
              <div className="flex items-center gap-2 mb-2">
                <Flame className="w-4 h-4 text-red-600" />
                <span className="font-semibold text-gray-900 text-sm">Vol Breakout</span>
              </div>
              <p className="text-xs text-gray-600 mb-2">
                Donchian breakouts on volatile tech stocks (NVDA, TSLA, AMD...).
              </p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-red-600 font-medium">Daily</span>
                {signalsByStrategy['Volatility Breakout'] ? (
                  <span className="px-2 py-0.5 bg-red-200 text-red-800 rounded text-xs">
                    {signalsByStrategy['Volatility Breakout']}
                  </span>
                ) : (
                  <span className="px-2 py-0.5 bg-gray-200 text-gray-600 rounded text-xs">
                    Scanning
                  </span>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* Positions */}
          <Card
            title="Current Positions"
            help="What the bot is currently holding"
            badge={positions.length > 0 && (
              <span className="px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs font-medium">
                {positions.length} holding{positions.length > 1 ? 's' : ''}
              </span>
            )}
          >
            {positions.length > 0 ? (
              <div className="space-y-3">
                {positions.map((pos) => {
                  const info = ETF_INFO[pos.symbol] || { name: pos.symbol, description: 'ETF' };
                  const botPos = botInsights?.positions.find(p => p.symbol === pos.symbol);
                  const strategy = botPos?.strategy || 'unknown';
                  const colors = STRATEGY_COLORS[strategy] || { bg: 'bg-gray-50', border: 'border-gray-300', text: 'text-gray-600' };
                  const stopDistance = botPos?.stop_distance_pct ? (botPos.stop_distance_pct * 100).toFixed(1) : null;
                  return (
                    <div key={pos.symbol} className={`rounded-lg p-3 border ${colors.bg} ${colors.border}`}>
                      <div className="flex justify-between items-start mb-1">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-lg font-bold text-gray-900">{pos.symbol}</span>
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${colors.text} ${colors.bg}`}>
                              {strategy === 'unknown' ? 'Manual' : strategy.replace('_', ' ')}
                            </span>
                          </div>
                          <p className="text-xs text-gray-500">{info.name} - {info.description}</p>
                        </div>
                        <div className={`px-2 py-0.5 rounded text-sm font-medium ${
                          pos.unrealized_pnl >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                        }`}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}{formatCurrency(pos.unrealized_pnl)}
                        </div>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>{pos.quantity} shares @ {formatCurrency(pos.avg_entry_price)}</span>
                        <span>{formatCurrency(pos.market_value)}</span>
                      </div>
                      {/* Trailing Stop Info */}
                      {botPos && (
                        <div className="mt-2 pt-2 border-t border-gray-200 grid grid-cols-3 gap-2 text-xs">
                          <div>
                            <span className="text-gray-400">Stop Loss</span>
                            <p className="font-medium text-red-600">{formatCurrency(botPos.stop_loss)}</p>
                          </div>
                          <div>
                            <span className="text-gray-400">Highest</span>
                            <p className="font-medium text-green-600">{formatCurrency(botPos.highest_price)}</p>
                          </div>
                          <div>
                            <span className="text-gray-400">Stop Distance</span>
                            <p className="font-medium text-gray-700">{stopDistance}%</p>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
                {/* Total Position Value */}
                <div className="border-t border-gray-200 pt-3 mt-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-semibold text-gray-700">Total Position Value</span>
                    <span className="text-lg font-bold text-gray-900">
                      {formatCurrency(positions.reduce((sum, pos) => sum + pos.market_value, 0))}
                    </span>
                  </div>
                  <div className="flex justify-between items-center mt-1">
                    <span className="text-xs text-gray-500">Total P&L</span>
                    <span className={`text-sm font-medium ${
                      positions.reduce((sum, pos) => sum + pos.unrealized_pnl, 0) >= 0
                        ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {positions.reduce((sum, pos) => sum + pos.unrealized_pnl, 0) >= 0 ? '+' : ''}
                      {formatCurrency(positions.reduce((sum, pos) => sum + pos.unrealized_pnl, 0))}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-6">
                <DollarSign className="w-10 h-10 text-gray-300 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">Holding cash</p>
                <p className="text-xs text-gray-400">Waiting for the right opportunity</p>
              </div>
            )}
          </Card>

          {/* Active Signals */}
          <Card
            title="Active Signals"
            help="Current recommendations from all strategies"
            badge={allSignals.length > 0 && (
              <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                {allSignals.length} total
              </span>
            )}
            className="lg:col-span-2"
          >
            {allSignals.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {allSignals.map((sig, idx) => {
                  const colors = STRATEGY_COLORS[sig.strategy] || STRATEGY_COLORS['Dual Momentum'];
                  return (
                    <div
                      key={`${sig.strategy}-${sig.symbol}-${idx}`}
                      className={`rounded-lg p-3 border ${colors.bg} ${colors.border} min-h-[70px]`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-1 rounded text-xs font-bold ${
                            sig.signal_type === 'BUY' ? 'bg-green-200 text-green-800' : 'bg-red-200 text-red-800'
                          }`}>
                            {sig.signal_type}
                          </span>
                          <span className="font-bold text-gray-900 text-sm">{sig.symbol}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <StrategyIcon strategy={sig.strategy} />
                          <span className={`text-xs ${colors.text}`}>{sig.strategy.split(' ')[0]}</span>
                        </div>
                      </div>
                      <p className="text-xs text-gray-600 leading-relaxed">{sig.description}</p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-6">
                <Activity className="w-10 h-10 text-gray-300 mx-auto mb-2" />
                <p className="text-gray-500 text-sm">Analyzing markets...</p>
              </div>
            )}
          </Card>
        </div>

        {/* Bot Insights - What the bot is thinking */}
        {botInsights && (
          <Card
            title="Bot Insights"
            help="What the trading bot is thinking and planning"
            className="mb-6"
            badge={
              <span className="flex items-center gap-2">
                {botInsights.summary.pending_action_count > 0 && (
                  <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded text-xs font-medium">
                    {botInsights.summary.pending_action_count} pending actions
                  </span>
                )}
                {botInsights.summary.new_candidates > 0 && (
                  <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                    {botInsights.summary.new_candidates} candidates
                  </span>
                )}
              </span>
            }
          >
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Market Phase */}
              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-gray-500" />
                  Market Phase
                </h4>
                <p className={`text-lg font-bold ${
                  botInsights.market_phase === 'opening_volatility' ? 'text-yellow-600' :
                  botInsights.market_phase === 'closing_action' ? 'text-orange-600' :
                  botInsights.market_phase === 'normal' ? 'text-green-600' :
                  'text-gray-600'
                }`}>
                  {botInsights.market_phase === 'opening_volatility' ? 'Opening (Volatile)' :
                   botInsights.market_phase === 'closing_action' ? 'Closing Soon' :
                   botInsights.market_phase === 'normal' ? 'Normal Trading' :
                   botInsights.market_phase === 'closed' ? 'Market Closed' :
                   botInsights.market_phase}
                </p>
                <div className="mt-2 text-xs text-gray-500">
                  <p>{botInsights.summary.total_positions} positions ({botInsights.summary.profitable_positions} profitable, {botInsights.summary.losing_positions} losing)</p>
                </div>
              </div>

              {/* Pending Actions */}
              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <Zap className="w-4 h-4 text-yellow-500" />
                  Pending Actions
                </h4>
                {botInsights.pending_actions.length > 0 ? (
                  <div className="space-y-2 max-h-32 overflow-y-auto">
                    {botInsights.pending_actions.map((pa, idx) => (
                      <div key={`${pa.symbol}-${idx}`} className="text-sm">
                        <span className="font-medium text-gray-900">{pa.symbol}</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {pa.actions.map((action, actionIdx) => (
                            <span
                              key={actionIdx}
                              className={`px-1.5 py-0.5 rounded text-xs ${
                                action.priority === 'high' ? 'bg-red-100 text-red-700' :
                                action.priority === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                                'bg-blue-100 text-blue-700'
                              }`}
                              title={action.description}
                            >
                              {action.action.replace('_', ' ')}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-400 text-sm">No pending actions</p>
                )}
              </div>

              {/* New Position Candidates */}
              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                  <Eye className="w-4 h-4 text-blue-500" />
                  Considering Buying
                </h4>
                {botInsights.new_position_candidates.length > 0 ? (
                  <div className="space-y-2 max-h-32 overflow-y-auto">
                    {botInsights.new_position_candidates.map((cand, idx) => {
                      const colors = STRATEGY_COLORS[cand.strategy] || STRATEGY_COLORS['Dual Momentum'];
                      return (
                        <div key={`${cand.symbol}-${idx}`} className={`p-2 rounded ${colors.bg} border ${colors.border}`}>
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-gray-900">{cand.symbol}</span>
                            <span className={`text-xs ${colors.text}`}>{cand.strategy.split(' ')[0]}</span>
                          </div>
                          <p className="text-xs text-gray-600 truncate" title={cand.reason}>{cand.reason}</p>
                          <div className="flex gap-2 mt-1 text-xs text-gray-500">
                            <span>Strength: {(cand.strength * 100).toFixed(0)}%</span>
                            {cand.momentum !== 0 && <span>Mom: {(cand.momentum * 100).toFixed(1)}%</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-gray-400 text-sm">No new positions being considered</p>
                )}
              </div>
            </div>

            {/* Active Signals from bot insights */}
            {(botInsights.active_signals.simple_momentum.length > 0 || botInsights.active_signals.pairs_trading.length > 0) && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Active Strategy Signals</h4>
                <div className="flex flex-wrap gap-2">
                  {botInsights.active_signals.simple_momentum.map((sig, idx) => (
                    <span
                      key={`mom-${idx}`}
                      className={`px-2 py-1 rounded text-xs ${
                        sig.action === 'BUY' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {sig.symbol} {sig.action} ({(sig.strength * 100).toFixed(0)}%)
                      {sig.in_position && ' [HOLDING]'}
                    </span>
                  ))}
                  {botInsights.active_signals.pairs_trading.map((sig, idx) => (
                    <span
                      key={`pair-${idx}`}
                      className={`px-2 py-1 rounded text-xs ${
                        sig.action === 'BUY' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {sig.symbol} {sig.action} (Pairs)
                      {sig.in_position && ' [HOLDING]'}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Card>
        )}

        {/* Pairs Trading Status */}
        {pairsStatus.length > 0 && (
          <Card
            title="Pairs Trading Status"
            help="Z-score shows how far apart paired ETFs are. Trade triggers at |z| > 2.0"
            className="mb-6"
          >
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {pairsStatus.map((pair) => (
                <div
                  key={pair.pair}
                  className={`rounded-lg p-3 text-center ${
                    pair.status === 'invalid' ? 'bg-gray-50' :
                    Math.abs(pair.z_score || 0) >= 2 ? 'bg-orange-100 border border-orange-300' :
                    Math.abs(pair.z_score || 0) >= 1 ? 'bg-yellow-50' : 'bg-green-50'
                  }`}
                >
                  <p className="font-semibold text-gray-900 text-sm">{pair.pair}</p>
                  {pair.status === 'invalid' ? (
                    <p className="text-xs text-gray-400">Low correlation</p>
                  ) : (
                    <>
                      <p className={`text-lg font-bold ${
                        Math.abs(pair.z_score || 0) >= 2 ? 'text-orange-600' :
                        Math.abs(pair.z_score || 0) >= 1 ? 'text-yellow-600' : 'text-green-600'
                      }`}>
                        {(pair.z_score || 0) >= 0 ? '+' : ''}{(pair.z_score || 0).toFixed(2)}
                      </p>
                      <p className="text-xs text-gray-500">corr: {((pair.correlation || 0) * 100).toFixed(0)}%</p>
                    </>
                  )}
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-3 text-center">
              Z-score: 0 = normal | ±1 = watching | ±2 = trade signal (pairs have diverged)
            </p>
          </Card>
        )}

        {/* Market Chart */}
        <Card
          title="S&P 500 (SPY) - Last 90 Days"
          help="The overall stock market. When this goes up, the economy is generally doing well."
          className="mb-6"
        >
          <div className="h-56">
            {marketData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={marketData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    tick={{ fontSize: 10 }}
                    stroke="#9ca3af"
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    tickFormatter={(v) => `$${v}`}
                    tick={{ fontSize: 10 }}
                    stroke="#9ca3af"
                    width={50}
                  />
                  <Tooltip
                    formatter={(value) => [formatCurrency(Number(value)), 'Price']}
                    labelFormatter={(label) => new Date(String(label)).toLocaleDateString()}
                  />
                  <Area type="monotone" dataKey="close" stroke="#3b82f6" fill="#93c5fd" fillOpacity={0.3} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400">
                Loading chart...
              </div>
            )}
          </div>
        </Card>

        {/* Bottom Grid: Safety + Performance */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Safety Controls */}
          <Card title="Safety Controls" help="Automatic protections to prevent big losses">
            {riskStatus ? (
              <div className="space-y-4">
                <div className={`flex items-center gap-3 p-3 rounded-lg ${
                  riskStatus.can_trade ? 'bg-green-50' : 'bg-red-50'
                }`}>
                  {riskStatus.can_trade ? (
                    <CheckCircle className="w-6 h-6 text-green-500" />
                  ) : (
                    <XCircle className="w-6 h-6 text-red-500" />
                  )}
                  <div>
                    <p className={`font-semibold ${riskStatus.can_trade ? 'text-green-800' : 'text-red-800'}`}>
                      {riskStatus.can_trade ? 'All Clear - Trading Enabled' : 'Trading Halted'}
                    </p>
                    {!riskStatus.can_trade && (
                      <p className="text-sm text-red-600">{riskStatus.halt_reason}</p>
                    )}
                  </div>
                </div>
                <div className="space-y-3 text-sm">
                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-gray-600">Daily Loss Limit</span>
                      <span className="text-gray-500">Max -2%</span>
                    </div>
                    <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div className="h-full bg-green-500 rounded-full" style={{ width: '5%' }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-gray-600">Max Drawdown</span>
                      <span className="text-gray-500">Max -15%</span>
                    </div>
                    <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div className="h-full bg-green-500 rounded-full" style={{ width: '3%' }} />
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-gray-400 text-center py-6">Loading...</div>
            )}
          </Card>

          {/* Strategy Performance */}
          <Card title="Strategy Performance" help="How each strategy compares to the S&P 500">
            {strategies.length > 0 ? (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {strategies.map((strat) => {
                  const benchmark = strategies.find(s => s.status === 'benchmark');
                  const beating = benchmark && strat.status !== 'benchmark' && strat.total_return > benchmark.total_return;
                  return (
                    <div
                      key={strat.name}
                      className={`rounded-lg p-3 ${
                        strat.status === 'benchmark' ? 'bg-gray-100' :
                        beating ? 'bg-green-50 border border-green-200' : 'bg-yellow-50 border border-yellow-200'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900">{strat.name}</span>
                          {strat.status === 'benchmark' && (
                            <span className="px-1.5 py-0.5 bg-gray-300 text-gray-600 text-xs rounded">BENCHMARK</span>
                          )}
                          {beating && (
                            <TrendingUp className="w-4 h-4 text-green-500" />
                          )}
                        </div>
                        <span className={`font-bold ${strat.total_return >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {strat.total_return >= 0 ? '+' : ''}{formatPercent(strat.total_return)}
                        </span>
                      </div>
                      <div className="flex gap-4 mt-1 text-xs text-gray-500">
                        <span>Sharpe: {strat.sharpe_ratio.toFixed(2)}</span>
                        <span>Max DD: {formatPercent(strat.max_drawdown)}</span>
                        <span>Trades: {strat.trade_count}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-gray-400 text-center py-6">Loading strategies...</div>
            )}
          </Card>
        </div>

        {/* Recent Trades */}
        <Card title="Recent Trades" help="Buy and sell activity">
          {trades.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-2">Date</th>
                    <th className="pb-2">Action</th>
                    <th className="pb-2 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.slice(0, 8).map((trade) => (
                    <tr key={trade.id} className="border-b border-gray-100">
                      <td className="py-2 text-gray-500">{new Date(trade.timestamp).toLocaleDateString()}</td>
                      <td className="py-2">
                        <span className={`font-medium ${trade.action === 'BUY' ? 'text-green-600' : 'text-red-600'}`}>
                          {trade.action}
                        </span> {trade.quantity} {trade.symbol}
                      </td>
                      <td className="py-2 text-right font-medium">{formatCurrency(trade.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-6 text-gray-400">
              <p>No trades yet</p>
            </div>
          )}
        </Card>

        {/* Daily Performance Journal */}
        <Card
          title="Daily Performance Journal"
          help="Track your daily P&L and notes"
          className="mt-6"
          badge={
            <button
              onClick={() => setShowJournalForm(!showJournalForm)}
              className="flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium hover:bg-blue-200"
            >
              <Plus className="w-3 h-3" />
              Add Entry
            </button>
          }
        >
          {/* Journal Form */}
          {showJournalForm && (
            <form onSubmit={handleJournalSubmit} className="mb-4 p-4 bg-gray-50 rounded-lg">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Date</label>
                  <input
                    type="date"
                    value={journalForm.date}
                    onChange={(e) => setJournalForm({ ...journalForm, date: e.target.value })}
                    className="w-full px-2 py-1 border rounded text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Starting Equity</label>
                  <input
                    type="number"
                    step="0.01"
                    value={journalForm.starting_equity}
                    onChange={(e) => setJournalForm({ ...journalForm, starting_equity: e.target.value })}
                    placeholder="100000.00"
                    className="w-full px-2 py-1 border rounded text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Ending Equity</label>
                  <input
                    type="number"
                    step="0.01"
                    value={journalForm.ending_equity}
                    onChange={(e) => setJournalForm({ ...journalForm, ending_equity: e.target.value })}
                    placeholder="100500.00"
                    className="w-full px-2 py-1 border rounded text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Notes (optional)</label>
                  <input
                    type="text"
                    value={journalForm.notes}
                    onChange={(e) => setJournalForm({ ...journalForm, notes: e.target.value })}
                    placeholder="Market was volatile..."
                    className="w-full px-2 py-1 border rounded text-sm"
                  />
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                <button
                  type="submit"
                  className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
                >
                  Save Entry
                </button>
                <button
                  type="button"
                  onClick={() => setShowJournalForm(false)}
                  className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          {/* Journal Summary */}
          {journalSummary && journalSummary.total_entries > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500">Total P&L</p>
                <p className={`text-lg font-bold ${journalSummary.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {journalSummary.total_pnl >= 0 ? '+' : ''}{formatCurrency(journalSummary.total_pnl)}
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500">Win Rate</p>
                <p className="text-lg font-bold text-gray-900">{journalSummary.win_rate}%</p>
                <p className="text-xs text-gray-400">{journalSummary.winning_days}W / {journalSummary.losing_days}L</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500">Avg Daily</p>
                <p className={`text-lg font-bold ${journalSummary.average_daily_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {journalSummary.average_daily_pnl >= 0 ? '+' : ''}{formatCurrency(journalSummary.average_daily_pnl)}
                </p>
              </div>
              <div className="bg-green-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500">Best Day</p>
                {journalSummary.best_day && (
                  <>
                    <p className="text-lg font-bold text-green-600">+{formatCurrency(journalSummary.best_day.pnl)}</p>
                    <p className="text-xs text-gray-400">{journalSummary.best_day.date}</p>
                  </>
                )}
              </div>
              <div className="bg-red-50 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-500">Worst Day</p>
                {journalSummary.worst_day && (
                  <>
                    <p className="text-lg font-bold text-red-600">{formatCurrency(journalSummary.worst_day.pnl)}</p>
                    <p className="text-xs text-gray-400">{journalSummary.worst_day.date}</p>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Journal Entries Table */}
          {journalEntries.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-2">Date</th>
                    <th className="pb-2 text-right">Starting</th>
                    <th className="pb-2 text-right">Ending</th>
                    <th className="pb-2 text-right">P&L</th>
                    <th className="pb-2 text-right">%</th>
                    <th className="pb-2">Notes</th>
                    <th className="pb-2 w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {journalEntries.slice(0, 10).map((entry) => (
                    <tr key={entry.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 text-gray-700 flex items-center gap-1">
                        <Calendar className="w-3 h-3 text-gray-400" />
                        {entry.date}
                      </td>
                      <td className="py-2 text-right text-gray-500">{formatCurrency(entry.starting_equity)}</td>
                      <td className="py-2 text-right text-gray-700">{formatCurrency(entry.ending_equity)}</td>
                      <td className={`py-2 text-right font-medium ${entry.daily_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {entry.daily_pnl >= 0 ? '+' : ''}{formatCurrency(entry.daily_pnl)}
                      </td>
                      <td className={`py-2 text-right font-medium ${entry.daily_pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {entry.daily_pnl_pct >= 0 ? '+' : ''}{entry.daily_pnl_pct.toFixed(2)}%
                      </td>
                      <td className="py-2 text-gray-500 text-xs max-w-32 truncate" title={entry.notes}>
                        {entry.notes || '-'}
                      </td>
                      <td className="py-2">
                        <button
                          onClick={() => handleDeleteJournal(entry.date)}
                          className="p-1 text-gray-400 hover:text-red-500"
                          title="Delete entry"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400">
              <BookOpen className="w-10 h-10 mx-auto mb-2" />
              <p className="text-sm">No journal entries yet</p>
              <p className="text-xs">Click "Add Entry" to start tracking your daily P&L</p>
            </div>
          )}
        </Card>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 px-6 py-3 mt-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-xs text-gray-500">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse"></span>
            <span>Paper Trading Mode (simulated money)</span>
          </div>
          <span>Auto-refreshes every 60s</span>
        </div>
      </footer>
    </div>
  );
}
