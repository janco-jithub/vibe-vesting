"""
Machine Learning Momentum Strategy using Gradient Boosting.

Based on academic research:
- Gu, S., Kelly, B., & Xiu, D. (2020). "Empirical Asset Pricing via Machine Learning."
  Review of Financial Studies.
- Uses LightGBM for return prediction with technical features

This strategy:
1. Engineers technical features (momentum, volatility, trend indicators)
2. Trains a gradient boosting model to predict next-day returns
3. Generates signals based on predicted return magnitude

Works great on Mac M2 - LightGBM is CPU-based and M2 is fast!
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging
import pickle

import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams


logger = logging.getLogger(__name__)


@dataclass
class MLPrediction:
    """ML model prediction for a symbol."""
    symbol: str
    predicted_return: float
    confidence: float
    features: Dict[str, float]


class MLMomentumStrategy(BaseStrategy):
    """
    ML-Based Momentum Strategy using Gradient Boosting.

    Uses LightGBM to predict next-day returns based on technical features:
    - Momentum (various lookbacks: 5, 10, 20, 60 days)
    - Volatility (realized vol, ATR)
    - Trend indicators (MA ratios, price position)
    - Volume features (volume momentum, relative volume)

    The model is trained with walk-forward validation to avoid look-ahead bias.

    Academic Performance (Gu et al. 2020):
    - Out-of-sample R² of 0.5-1% (significant for daily returns)
    - Sharpe ratio improvements over traditional factors
    """

    DEFAULT_UNIVERSE = [
        "SPY", "QQQ", "IWM",  # Broad market
        "XLF", "XLK", "XLE", "XLV", "XLI", "XLU",  # Sectors
    ]

    MODEL_DIR = Path("models/ml_momentum")

    def __init__(
        self,
        universe: Optional[List[str]] = None,
        prediction_threshold: float = 0.002,  # Lower threshold = more signals
        retrain_days: int = 30,  # More frequent retraining for adaptation
        lookback_days: int = 252,  # 1 year training - works with our data
        prediction_horizon: int = 5,  # Predict 1-week returns - faster signals
        use_trend_filter: bool = False,  # Disable filter for bull market capture
        name: str = "ml_momentum"
    ):
        """
        Initialize ML Momentum Strategy.

        IMPROVED VERSION:
        - Predict monthly returns instead of daily (less noise)
        - Longer training period (3 years instead of 1 year)
        - Less frequent retraining (90 days instead of 30, reduce overfitting)
        - Add trend filter (200-day MA per Faber 2007)
        - Higher prediction threshold (1% monthly vs 0.2% daily)

        Args:
            universe: List of symbols to trade
            prediction_threshold: Minimum predicted return to generate signal
            retrain_days: Days between model retraining
            lookback_days: Training data lookback period
            prediction_horizon: Days ahead to predict (default: 21 = 1 month)
            use_trend_filter: Apply 200-day MA filter
            name: Strategy identifier
        """
        self.prediction_threshold = prediction_threshold
        self.retrain_days = retrain_days
        self.lookback_days = lookback_days
        self.prediction_horizon = prediction_horizon
        self.use_trend_filter = use_trend_filter

        universe = universe or self.DEFAULT_UNIVERSE
        super().__init__(name=name, universe=universe)

        # Model components
        self.models: Dict[str, lgb.Booster] = {}
        self.scalers: Dict[str, StandardScaler] = {}
        self.last_train_date: Optional[date] = None
        self.feature_names: List[str] = []

        # Ensure model directory exists
        self.MODEL_DIR.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Initialized MLMomentumStrategy",
            extra={
                "universe_size": len(self.universe),
                "prediction_threshold": prediction_threshold,
                "retrain_days": retrain_days
            }
        )

    def _calculate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical features for ML model.

        Features based on Gu et al. (2020) and standard quant factors:
        - Momentum at various horizons
        - Volatility measures
        - Trend indicators
        - Volume features

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with calculated features
        """
        features = pd.DataFrame(index=df.index)
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # === Momentum Features ===
        # Returns at various lookbacks
        for period in [1, 5, 10, 20, 60]:
            features[f'ret_{period}d'] = close.pct_change(period)

        # Momentum (past returns, excluding most recent day to avoid reversal)
        features['mom_5d'] = close.shift(1).pct_change(5)
        features['mom_10d'] = close.shift(1).pct_change(10)
        features['mom_20d'] = close.shift(1).pct_change(20)
        features['mom_60d'] = close.shift(1).pct_change(60)

        # === Volatility Features ===
        # Realized volatility
        returns = close.pct_change()
        features['vol_5d'] = returns.rolling(5).std() * np.sqrt(252)
        features['vol_20d'] = returns.rolling(20).std() * np.sqrt(252)
        features['vol_60d'] = returns.rolling(60).std() * np.sqrt(252)

        # Average True Range (ATR)
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        features['atr_14d'] = tr.rolling(14).mean() / close

        # Volatility change
        features['vol_change'] = features['vol_5d'] / features['vol_20d'] - 1

        # === Trend Features ===
        # Moving average ratios
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()

        features['ma_5_20_ratio'] = ma5 / ma20 - 1
        features['ma_10_50_ratio'] = ma10 / ma50 - 1
        features['price_ma20_ratio'] = close / ma20 - 1
        features['price_ma50_ratio'] = close / ma50 - 1

        # Price position in range
        high_20d = high.rolling(20).max()
        low_20d = low.rolling(20).min()
        features['price_position_20d'] = (close - low_20d) / (high_20d - low_20d + 1e-8)

        high_60d = high.rolling(60).max()
        low_60d = low.rolling(60).min()
        features['price_position_60d'] = (close - low_60d) / (high_60d - low_60d + 1e-8)

        # === RSI ===
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / (avg_loss + 1e-8)
        features['rsi_14'] = 100 - (100 / (1 + rs))
        features['rsi_14_norm'] = (features['rsi_14'] - 50) / 50  # Normalize to [-1, 1]

        # === Volume Features ===
        vol_ma20 = volume.rolling(20).mean()
        features['vol_ratio'] = volume / (vol_ma20 + 1e-8)
        features['vol_momentum'] = volume.pct_change(5)

        # Volume-price relationship
        features['price_vol_corr'] = close.rolling(20).corr(volume)

        # === Day of Week (if datetime index) ===
        if hasattr(df.index, 'dayofweek'):
            features['day_of_week'] = df.index.dayofweek / 4  # Normalize to [0, 1]

        # Store feature names
        self.feature_names = list(features.columns)

        return features

    def _prepare_training_data(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prepare training data for all symbols.

        Args:
            data: Market data dict
            as_of_date: Train using data up to this date

        Returns:
            Tuple of (features DataFrame, target Series)
        """
        all_features = []
        all_targets = []

        for symbol in self.universe:
            if symbol not in data or data[symbol].empty:
                continue

            df = data[symbol].copy()

            # Filter to training period
            mask = df.index.date <= as_of_date
            df = df[mask]

            if len(df) < 100:  # Need enough data
                continue

            # Calculate features
            features = self._calculate_features(df)

            # Target: next-month return (CHANGED from next-day)
            # Predict 21-day forward return (1 month) - more predictable than daily
            target = df['close'].pct_change(self.prediction_horizon).shift(-self.prediction_horizon)

            # Add symbol identifier
            features['symbol'] = symbol

            # Remove rows with NaN
            valid_mask = features.notna().all(axis=1) & target.notna()
            features = features[valid_mask]
            target = target[valid_mask]

            all_features.append(features)
            all_targets.append(target)

        if not all_features:
            return pd.DataFrame(), pd.Series()

        X = pd.concat(all_features, axis=0)
        y = pd.concat(all_targets, axis=0)

        return X, y

    def train_model(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> None:
        """
        Train the ML model using walk-forward validation.

        Args:
            data: Market data dict
            as_of_date: Train using data up to this date
        """
        logger.info(f"Training ML model as of {as_of_date}")

        # Prepare training data
        X, y = self._prepare_training_data(data, as_of_date)

        if X.empty:
            logger.warning("No training data available")
            return

        # Separate symbol column
        symbols = X['symbol']
        X = X.drop('symbol', axis=1)

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        X_scaled = pd.DataFrame(X_scaled, columns=X.columns, index=X.index)

        # Time-series cross-validation
        tscv = TimeSeriesSplit(n_splits=5)

        # LightGBM parameters (tuned for financial data)
        # IMPROVED: Stronger regularization to reduce overfitting
        params = {
            'objective': 'regression',
            'metric': 'mse',
            'boosting_type': 'gbdt',
            'num_leaves': 20,  # REDUCED from 31 (less overfitting)
            'learning_rate': 0.03,  # REDUCED from 0.05 (slower, more stable)
            'feature_fraction': 0.7,  # REDUCED from 0.8 (more regularization)
            'bagging_fraction': 0.7,  # REDUCED from 0.8 (more regularization)
            'bagging_freq': 5,
            'min_child_samples': 50,  # NEW: Require more samples per leaf
            'lambda_l1': 0.5,  # NEW: L1 regularization
            'lambda_l2': 0.5,  # NEW: L2 regularization
            'verbose': -1,
            'n_jobs': -1,  # Use all cores (M2 has good multi-core)
            'seed': 42,
        }

        # Train with early stopping using last fold
        best_iteration = 100

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X_scaled)):
            X_train = X_scaled.iloc[train_idx]
            y_train = y.iloc[train_idx]
            X_val = X_scaled.iloc[val_idx]
            y_val = y.iloc[val_idx]

            train_data = lgb.Dataset(X_train, label=y_train)
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

            model = lgb.train(
                params,
                train_data,
                num_boost_round=500,
                valid_sets=[val_data],
                callbacks=[
                    lgb.early_stopping(stopping_rounds=50),
                    lgb.log_evaluation(period=0)  # Suppress logging
                ]
            )

            best_iteration = max(best_iteration, model.best_iteration)

        # Final model trained on all data
        train_data = lgb.Dataset(X_scaled, label=y)
        final_model = lgb.train(
            params,
            train_data,
            num_boost_round=best_iteration
        )

        # Store model and scaler
        self.models['combined'] = final_model
        self.scalers['combined'] = scaler
        self.last_train_date = as_of_date

        # Log feature importance
        importance = pd.DataFrame({
            'feature': X.columns,
            'importance': final_model.feature_importance(importance_type='gain')
        }).sort_values('importance', ascending=False)

        logger.info(
            "Model trained successfully",
            extra={
                "samples": len(X),
                "features": len(X.columns),
                "best_iteration": best_iteration,
                "top_features": importance.head(5)['feature'].tolist()
            }
        )

        # Save model
        self._save_model()

    def _save_model(self) -> None:
        """Save model to disk."""
        if 'combined' not in self.models:
            return

        model_path = self.MODEL_DIR / "model.txt"
        scaler_path = self.MODEL_DIR / "scaler.pkl"
        meta_path = self.MODEL_DIR / "metadata.pkl"

        self.models['combined'].save_model(str(model_path))

        with open(scaler_path, 'wb') as f:
            pickle.dump(self.scalers['combined'], f)

        with open(meta_path, 'wb') as f:
            pickle.dump({
                'last_train_date': self.last_train_date,
                'feature_names': self.feature_names
            }, f)

        logger.info(f"Model saved to {self.MODEL_DIR}")

    def _load_model(self) -> bool:
        """Load model from disk if available."""
        model_path = self.MODEL_DIR / "model.txt"
        scaler_path = self.MODEL_DIR / "scaler.pkl"
        meta_path = self.MODEL_DIR / "metadata.pkl"

        if not all(p.exists() for p in [model_path, scaler_path, meta_path]):
            return False

        try:
            self.models['combined'] = lgb.Booster(model_file=str(model_path))

            with open(scaler_path, 'rb') as f:
                self.scalers['combined'] = pickle.load(f)

            with open(meta_path, 'rb') as f:
                meta = pickle.load(f)
                self.last_train_date = meta['last_train_date']
                self.feature_names = meta['feature_names']

            logger.info(f"Model loaded from {self.MODEL_DIR}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def _needs_retraining(self, as_of_date: date) -> bool:
        """Check if model needs retraining."""
        if 'combined' not in self.models:
            return True

        if self.last_train_date is None:
            return True

        days_since_train = (as_of_date - self.last_train_date).days
        return days_since_train >= self.retrain_days

    def _predict(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> List[MLPrediction]:
        """
        Generate predictions for all symbols.

        Args:
            data: Market data dict
            as_of_date: Predict as of this date

        Returns:
            List of MLPrediction objects
        """
        predictions = []

        if 'combined' not in self.models:
            return predictions

        model = self.models['combined']
        scaler = self.scalers['combined']

        for symbol in self.universe:
            if symbol not in data or data[symbol].empty:
                continue

            df = data[symbol].copy()
            mask = df.index.date <= as_of_date
            df = df[mask]

            if len(df) < 100:
                continue

            # Calculate features for latest day
            features = self._calculate_features(df)

            if features.empty:
                continue

            # Get latest features
            latest = features.iloc[-1:].copy()

            # Ensure we have all expected features
            for feat in self.feature_names:
                if feat not in latest.columns:
                    latest[feat] = 0.0

            latest = latest[self.feature_names]

            if latest.isna().any().any():
                continue

            # Scale and predict
            X_scaled = scaler.transform(latest)
            pred_return = model.predict(X_scaled)[0]

            # Calculate confidence based on feature values
            # Higher RSI extremes and momentum = higher confidence
            rsi = latest['rsi_14_norm'].iloc[0] if 'rsi_14_norm' in latest.columns else 0
            mom = latest['mom_20d'].iloc[0] if 'mom_20d' in latest.columns else 0
            confidence = min(1.0, abs(pred_return) * 50 + abs(rsi) * 0.3 + abs(mom) * 2)

            predictions.append(MLPrediction(
                symbol=symbol,
                predicted_return=float(pred_return),
                confidence=float(confidence),
                features={col: float(latest[col].iloc[0]) for col in latest.columns[:5]}
            ))

        # Sort by predicted return magnitude
        predictions.sort(key=lambda x: abs(x.predicted_return), reverse=True)

        return predictions

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        Generate trading signals based on ML predictions.

        Args:
            data: Dict mapping symbol to DataFrame with OHLCV data

        Returns:
            List of Signal objects
        """
        self.validate_data(data)

        signals = []

        # Get all dates
        ref_symbol = self.universe[0]
        all_dates = data[ref_symbol].index

        if len(all_dates) < 100:
            logger.warning("Insufficient data for ML strategy")
            return signals

        # Start after initial training period
        start_idx = 100

        for i in range(start_idx, len(all_dates)):
            current_date = all_dates[i]
            if hasattr(current_date, 'date'):
                current_date = current_date.date()

            # Check if we need to train/retrain
            if self._needs_retraining(current_date):
                self.train_model(data, current_date)

            # Generate predictions
            predictions = self._predict(data, current_date)

            # Convert predictions to signals
            for pred in predictions:
                if abs(pred.predicted_return) >= self.prediction_threshold:
                    # Apply trend filter (Faber 2007)
                    if self.use_trend_filter and pred.predicted_return > 0:
                        # Check if symbol is above 200-day MA
                        if pred.symbol in data and not data[pred.symbol].empty:
                            df = data[pred.symbol]
                            mask = df.index.date <= current_date
                            prices = df[mask]["close"]

                            if len(prices) >= 200:
                                current_price = prices.iloc[-1]
                                ma_200 = prices.rolling(200).mean().iloc[-1]

                                # CRITICAL: Don't buy below trend
                                if current_price < ma_200:
                                    logger.debug(
                                        f"ML: Skipping {pred.symbol} - positive prediction but below 200-MA"
                                    )
                                    continue

                    signal_type = SignalType.BUY if pred.predicted_return > 0 else SignalType.SELL
                    strength = min(1.0, abs(pred.predicted_return) / (self.prediction_threshold * 3))

                    signals.append(Signal(
                        date=current_date,
                        symbol=pred.symbol,
                        signal_type=signal_type,
                        strength=strength,
                        metadata={
                            "strategy": self.name,
                            "predicted_return": pred.predicted_return,
                            "confidence": pred.confidence,
                            "top_features": pred.features,
                            "prediction_horizon": self.prediction_horizon
                        }
                    ))

        logger.info(f"Generated {len(signals)} ML signals")
        return signals

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
        current_positions: Dict[str, float]
    ) -> float:
        """
        Calculate position size based on prediction confidence.

        Uses Kelly-inspired sizing: higher confidence = larger position.
        Max 10% per position for diversification.
        """
        if signal.signal_type == SignalType.SELL:
            return 0.0

        if signal.signal_type == SignalType.HOLD:
            return current_positions.get(signal.symbol, 0.0)

        # Max 10% per position
        max_position = portfolio_value * 0.10

        # Scale by signal strength and predicted return confidence
        pred_return = signal.metadata.get('predicted_return', 0) if signal.metadata else 0
        confidence = signal.metadata.get('confidence', 0.5) if signal.metadata else 0.5

        # Position size scales with confidence
        target_size = max_position * signal.strength * confidence

        return min(target_size, max_position)

    def get_backtest_params(self) -> BacktestParams:
        """Return default backtesting parameters."""
        return BacktestParams(
            start_date="2022-01-01",
            end_date="2024-12-31",
            initial_capital=10000.0,
            rebalance_frequency="daily",
            transaction_cost_bps=10,
            slippage_bps=10
        )

    def get_required_history(self) -> int:
        """Return required historical data length."""
        return max(100, self.lookback_days)

    def get_current_signal(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[date] = None
    ) -> List[Signal]:
        """
        Get current ML-based trading signals.

        Args:
            data: Market data
            as_of_date: Date for signals (default: latest)

        Returns:
            List of current signals
        """
        if as_of_date is None:
            ref_symbol = self.universe[0]
            if ref_symbol in data and not data[ref_symbol].empty:
                as_of_date = data[ref_symbol].index[-1]
                if hasattr(as_of_date, 'date'):
                    as_of_date = as_of_date.date()
            else:
                return []

        # Try to load existing model
        if 'combined' not in self.models:
            self._load_model()

        # Train if needed
        if self._needs_retraining(as_of_date):
            self.train_model(data, as_of_date)

        # Generate predictions
        predictions = self._predict(data, as_of_date)
        signals = []

        for pred in predictions:
            if abs(pred.predicted_return) >= self.prediction_threshold:
                signal_type = SignalType.BUY if pred.predicted_return > 0 else SignalType.SELL
                strength = min(1.0, abs(pred.predicted_return) / (self.prediction_threshold * 3))

                signals.append(Signal(
                    date=as_of_date,
                    symbol=pred.symbol,
                    signal_type=signal_type,
                    strength=strength,
                    metadata={
                        "strategy": self.name,
                        "predicted_return": pred.predicted_return,
                        "confidence": pred.confidence,
                        "model_date": str(self.last_train_date)
                    }
                ))

        return signals
