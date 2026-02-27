#!/usr/bin/env python3
"""
Generate comprehensive backtest report from database results.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime
from data.storage import TradingDatabase

def generate_report():
    """Generate comprehensive backtest report."""

    db = TradingDatabase()

    print("\n" + "=" * 100)
    print("BACKTEST REPORT - PROFESSIONAL QUANTITATIVE ANALYSIS")
    print("=" * 100)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100 + "\n")

    # Load backtest results
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query("""
                SELECT
                    strategy_name,
                    run_date,
                    start_date,
                    end_date,
                    initial_capital,
                    final_equity,
                    total_return,
                    cagr,
                    sharpe_ratio,
                    sortino_ratio,
                    calmar_ratio,
                    max_drawdown,
                    win_rate,
                    profit_factor,
                    trade_count,
                    alpha,
                    beta
                FROM backtest_results
                ORDER BY run_date DESC, sharpe_ratio DESC
            """, conn)
    except Exception as e:
        print(f"Error loading results: {e}")
        return

    if df.empty:
        print("No backtest results found in database.")
        return

    # Get most recent run for each strategy
    latest_results = df.groupby('strategy_name').first().reset_index()

    print("## STRATEGY PERFORMANCE SUMMARY")
    print("-" * 100)
    print(f"{'Strategy':<25} {'Sharpe':<8} {'CAGR':<10} {'Return':<10} {'Max DD':<10} {'Trades':<8} {'Status':<15}")
    print("-" * 100)

    recommendations = []

    for _, row in latest_results.iterrows():
        strategy = row['strategy_name']
        sharpe = row['sharpe_ratio']
        cagr = row['cagr']
        ret = row['total_return']
        dd = row['max_drawdown']
        trades = row['trade_count']

        # Determine status
        if sharpe >= 1.5 and dd > -0.25 and trades >= 10:
            status = "EXCELLENT"
            rec = f"RECOMMENDED: {strategy} shows strong risk-adjusted returns"
            recommendations.append((1, rec, row))
        elif sharpe >= 1.0 and dd > -0.30 and trades >= 10:
            status = "GOOD"
            rec = f"VIABLE: {strategy} meets minimum requirements"
            recommendations.append((2, rec, row))
        elif sharpe >= 0.5 and trades >= 5:
            status = "NEEDS WORK"
            rec = f"NEEDS OPTIMIZATION: {strategy} requires parameter tuning"
            recommendations.append((3, rec, row))
        else:
            status = "NOT VIABLE"
            rec = f"NOT RECOMMENDED: {strategy} does not meet professional standards"
            recommendations.append((4, rec, row))

        print(f"{strategy:<25} {sharpe:>7.2f} {cagr:>9.1%} {ret:>9.1%} {dd:>9.1%} {trades:>7} {status:<15}")

    print("-" * 100)
    print()

    # Detailed analysis of best strategy
    best_strategy = latest_results.loc[latest_results['sharpe_ratio'].idxmax()]

    print("## BEST PERFORMING STRATEGY")
    print("-" * 100)
    print(f"Strategy: {best_strategy['strategy_name']}")
    print(f"Backtest Period: {best_strategy['start_date']} to {best_strategy['end_date']}")
    print()
    print(f"Performance Metrics:")
    print(f"  - Sharpe Ratio:      {best_strategy['sharpe_ratio']:.2f}")
    print(f"  - Sortino Ratio:     {best_strategy['sortino_ratio']:.2f}")
    print(f"  - Calmar Ratio:      {best_strategy['calmar_ratio']:.2f}")
    print()
    print(f"Returns:")
    print(f"  - Total Return:      {best_strategy['total_return']:.1%}")
    print(f"  - CAGR:              {best_strategy['cagr']:.1%}")
    print(f"  - Max Drawdown:      {best_strategy['max_drawdown']:.1%}")
    print()
    print(f"Trading Activity:")
    print(f"  - Total Trades:      {best_strategy['trade_count']}")
    print(f"  - Win Rate:          {best_strategy['win_rate']:.1%}")
    print(f"  - Profit Factor:     {best_strategy['profit_factor']:.2f}")
    print()
    if best_strategy['alpha'] and best_strategy['beta']:
        print(f"vs Benchmark (SPY):")
        print(f"  - Alpha:             {best_strategy['alpha']:.1%}")
        print(f"  - Beta:              {best_strategy['beta']:.2f}")
    print("-" * 100)
    print()

    # Recommendations
    recommendations.sort(key=lambda x: x[0])

    print("## RECOMMENDATIONS")
    print("-" * 100)

    # Professional standards reference
    print("\nPROFESSIONAL STANDARDS (Academic Research):")
    print("  - Minimum Sharpe Ratio: 1.0 (industry standard)")
    print("  - Target Sharpe Ratio: 1.5+ (institutional quality)")
    print("  - Maximum Drawdown: < 25% (risk management)")
    print("  - Minimum Sample: 100+ trades for statistical significance")
    print()

    print("STRATEGY-SPECIFIC RECOMMENDATIONS:")
    for priority, rec, row in recommendations:
        print(f"  {priority}. {rec}")
        if priority <= 2:  # Show allocation for recommended strategies
            # Calculate suggested allocation
            if row['sharpe_ratio'] >= 1.5:
                allocation = 40
            elif row['sharpe_ratio'] >= 1.0:
                allocation = 30
            else:
                allocation = 20
            print(f"     Suggested Allocation: {allocation}% of capital")
            print(f"     Expected Annual Return: {row['cagr']:.1%}")
            print(f"     Risk (Max DD): {row['max_drawdown']:.1%}")
        print()

    print("-" * 100)
    print()

    # Key Findings
    print("## KEY FINDINGS")
    print("-" * 100)

    viable_count = len([r for r in recommendations if r[0] <= 2])
    total_count = len(recommendations)

    print(f"1. Strategies Tested: {total_count}")
    print(f"2. Viable Strategies: {viable_count}")
    print(f"3. Best Sharpe Ratio: {latest_results['sharpe_ratio'].max():.2f}")
    print(f"4. Average Sharpe: {latest_results['sharpe_ratio'].mean():.2f}")
    print()

    if viable_count == 0:
        print("CRITICAL FINDING:")
        print("  No strategies currently meet professional standards for live trading.")
        print("  All strategies require optimization before deploying real capital.")
        print()
        print("  Common issues:")
        print("  - Insufficient historical data (need 2+ years)")
        print("  - Parameters not optimized")
        print("  - Transaction costs too high relative to returns")
        print("  - Market regime mismatch (strategies optimized for different conditions)")
    else:
        print(f"POSITIVE FINDING:")
        print(f"  {viable_count} strategy(s) meet minimum requirements for live trading.")
        print(f"  These can be deployed with appropriate position sizing.")

    print("-" * 100)
    print()

    # Next Steps
    print("## RECOMMENDED NEXT STEPS")
    print("-" * 100)
    print("1. Fetch Additional Historical Data:")
    print("   - Minimum 2 years (500+ trading days) per symbol")
    print("   - Use: python scripts/fetch_historical_data.py --start-date 2022-01-01")
    print()
    print("2. Run Full Validation:")
    print("   - Monte Carlo simulation (100+ iterations)")
    print("   - Parameter sensitivity analysis")
    print("   - Regime analysis (bull/bear/sideways)")
    print("   - Use: python scripts/run_comprehensive_backtest.py --start-date 2022-01-01")
    print()
    print("3. Optimize Parameters:")
    print("   - Walk-forward optimization")
    print("   - Out-of-sample testing")
    print("   - Avoid overfitting")
    print()
    print("4. Paper Trading:")
    print("   - Test strategies for 3+ months")
    print("   - Verify Sharpe > 1.0 in live conditions")
    print("   - Monitor slippage and transaction costs")
    print()
    print("5. Risk Management:")
    print("   - Set maximum position size (20% per position)")
    print("   - Set maximum drawdown limit (20%)")
    print("   - Implement stop losses")
    print("   - Use Kelly Criterion for position sizing")
    print()
    print("-" * 100)
    print()

    # Academic References
    print("## ACADEMIC FOUNDATION")
    print("-" * 100)
    print("This analysis is based on peer-reviewed research:")
    print()
    print("1. Sharpe Ratio:")
    print("   Sharpe, W. F. (1994). The Sharpe Ratio. Journal of Portfolio Management.")
    print()
    print("2. Momentum Strategies:")
    print("   Jegadeesh, N., & Titman, S. (1993). Returns to Buying Winners and Selling Losers.")
    print("   Journal of Finance, 48(1), 65-91.")
    print()
    print("3. Backtest Overfitting:")
    print("   Bailey, D. H., et al. (2014). The Probability of Backtest Overfitting.")
    print("   Journal of Computational Finance.")
    print()
    print("4. Risk Management:")
    print("   Kelly, J. L. (1956). A New Interpretation of Information Rate.")
    print("   Bell System Technical Journal, 35(4), 917-926.")
    print("-" * 100)
    print()

    print("Report generation complete.")
    print(f"Database: {db.db_path}")
    print()

if __name__ == "__main__":
    generate_report()
