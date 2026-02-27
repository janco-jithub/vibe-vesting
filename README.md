# VIBE VESTING

### Because "Due Diligence" is just a vibe check on your portfolio

```
                         ____
                        /    \
    MY PORTFOLIO -->   | -2%  |    <-- "It's a long-term hold"
                        \____/
                          ||
                     _____|_____
                    |           |
                    |  DIAMOND  |
                    |   HANDS   |
                    |___________|
                      /       \
                     /  THIS   \
                    /  IS FINE  \
```

> "I didn't lose money, I just have unrealized lessons" - Sun Tzu, probably

---

## What is this?

An automated trading system built by someone who got tired of:
- Watching YouTube gurus tell me to "BUY NOW" from their rented Lamborghini
- Paying $997 for a Discord course that says "buy low sell high"
- Technical analysis that's basically astrology for men
- Staring at candles all day like it's a vigil for my portfolio

So I did what any reasonable person would do: I spent 6 months building a robot to lose money *faster* and *more efficiently* than I ever could manually.

---

## Features

| Feature | What Gurus Charge For This | What I Built It For |
|---------|---------------------------|---------------------|
| Multi-Factor Strategy | $2,997 "Elite Mentorship" | Mass amounts of caffeine |
| Kelly Position Sizing | $497/mo Discord | A Wikipedia article |
| VIX Regime Detection | "FREE WEBINAR" (it's never free) | Reading actual papers |
| Trailing Stop Losses | "Join My Inner Circle" | Common sense |
| Circuit Breakers | Not taught (they want you to blow up) | Pain |

---

## The Strategies

### Factor Composite
Combines Momentum, Quality, Low Volatility, and Value factors. Based on actual academic research, not a "golden cross" that some guy with a fake Rolex drew on a chart.

### Simple Momentum
"Number go up, I buy. Number go down, I sell." - literally 95% of all $4,999 trading courses condensed into one Python file.

### Pairs Trading
Statistical arbitrage. Or as I like to call it: "betting that things that should be the same price will eventually be the same price again." Revolutionary, I know.

### Dual Momentum
Based on Antonacci (2013) - an actual published paper, not a TikTok with rocket emojis.

---

## How It Actually Works

```
1. Robot wakes up
2. Checks if market is open (already smarter than 90% of crypto traders)
3. Downloads real data (not "signals" from a Telegram group)
4. Runs actual math (not drawing triangles on charts)
5. Calculates position sizes using Kelly Criterion
   (not "YOLO everything into one stock")
6. Places orders with stop losses
   (because unlike your favorite guru, I believe in risk management)
7. Goes back to sleep
8. Repeats
```

---

## Risk Management

> "Risk management? Where we're going, we don't need risk management"
> \- Every blown-up account ever

Unlike the "trust me bro" approach taught in most courses, this system has:

- **2% daily loss limit** - because drawdowns are not a "buying opportunity," they're a warning
- **15% max drawdown halt** - the machine literally turns itself off before going full WSB
- **Position sizing** - max 20% per trade, not "mortgage the house on TSLA weeklies"
- **Circuit breakers** - inspired by the stock exchange, not your uncle's "diamond hands" strategy
- **VIX monitoring** - when fear is high, we get small. When your guru says "blood in the streets," we're already hedged

---

## Performance

Let's be honest about backtests. Here's what the system *actually* did, not what I cherry-picked to sell you a course:

| Metric | Our System | Your Guru's "Guaranteed Returns" |
|--------|-----------|----------------------------------|
| Sharpe | ~0.45 | "10,000% (results not typical)" |
| Max Drawdown | -35% to -71% | Never mentioned |
| Win Rate | 44% | "98% win rate!!!" (on 3 trades) |
| Transparency | Open source | "Pay $997 to find out" |

**Is this good?** It's... honest. Which is more than any "FREE WEBINAR" has ever been.

---

## The Trading Guru Translation Guide

| What they say | What they mean |
|---------------|----------------|
| "Financial freedom" | I make money from courses, not trading |
| "This strategy made me millions" | My course sales made me millions |
| "Not financial advice" | It's definitely financial advice |
| "Diamond hands" | I'm too stubborn to cut my losses |
| "HODL" | I don't have a sell strategy |
| "Buy the dip" | Average down into a falling knife |
| "To the moon" | I need exit liquidity and you're it |
| "Trust the process" | I have no idea what I'm doing either |
| "Generational wealth" | The generation that lost it all |
| "I only share winners" | I delete the screenshots of my losses |
| "DM me for signals" | DM me your credit card details |
| "Technical Analysis" | Expensive crayons |

---

## Tech Stack

| Component | Technology | Guru Equivalent |
|-----------|------------|-----------------|
| Backend | Python | "My system uses proprietary AI" (it's an if-statement) |
| Data | Polygon.io + Alpaca | "I have insider connections" (it's a free API) |
| Database | SQLite | "Cloud-based infrastructure" (it's a file) |
| Frontend | React + Tailwind | "Custom dashboard worth $50K" (it's a div with CSS) |
| ML Model | scikit-learn | "Neural network AI" (it's linear regression) |
| Execution | Alpaca Paper Trading | "Live trading with millions" (it's fake money) |

---

## Quick Start

```bash
# 1. Clone (it's free, unlike everything else in trading)
git clone https://github.com/janco-jithub/vibe-vesting.git
cd vibe-vesting

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up your .env (keep your keys secret, unlike crypto influencers)
cp .env.example .env
# Edit .env with your Alpaca API keys

# 4. Download historical data (for backtesting, not for hindsight trading)
python -m scripts.backfill_historical --symbols SPY,QQQ,TLT,AAPL,GOOGL --days 365

# 5. Let the robot do what you can't: trade without emotions
python -m scripts.auto_trader --strategies factor_composite simple_momentum

# 6. Watch the dashboard and pretend you understand what's happening
./scripts/start_dashboard.sh
```

---

## Project Structure

```
vibe-vesting/
├── strategies/          # The actual alpha (free, btw)
├── risk/                # What every trading course skips
├── execution/           # Robot go brrr
├── data/                # Numbers (real ones, not made up)
├── backtest/            # Where dreams meet reality
├── monitoring/          # Making sure the robot hasn't gone sentient
├── frontend/            # Pretty charts to cope with
├── scripts/             # Press button, receive trades
└── tests/               # Yes, we test our code. Yes, it still breaks.
```

---

## FAQ

**Q: Will this make me rich?**
A: No. But it will make you less poor than following trading gurus.

**Q: Is this financial advice?**
A: Absolutely not. This is a cry for help wrapped in Python code.

**Q: Why is it called "Vibe Vesting"?**
A: Because "I automated my coping mechanism" was too long for a repo name.

**Q: Can I use this for real money?**
A: You *can*. Should you? Ask yourself: "Would I trust a robot built at 3 AM to manage my life savings?" Exactly.

**Q: Why not just buy index funds?**
A: Because then I'd have nothing to do at 3 AM except make healthy life choices.

**Q: What's your Sharpe ratio?**
A: Higher than zero but lower than what any guru claims. So, realistic.

**Q: Do you have a Discord?**
A: No. And if I ever start one that costs $97/month, please stage an intervention.

---

## Honest Disclaimer

This system trades with paper money. It has:
- Lost money
- Made money
- Confused me
- Made me mass amounts of trades at 3 AM
- Taught me more than any course ever did

The only guaranteed outcome of using this software is that you will learn Python. Whether you make money is between you and the market gods.

---

## Academic References

Unlike your favorite trading influencer, we cite our sources:

1. **Jegadeesh & Titman (1993)** - Momentum (the OG, not the TikTok version)
2. **Fama & French (1993, 2015)** - Factor models (actual Nobel Prize-winning work)
3. **Antonacci (2013)** - Dual Momentum (a real book, not a PDF from a Telegram group)
4. **Kelly (1956)** - Position sizing (math, not vibes)
5. **Kritzman et al. (2012)** - Regime detection (peer-reviewed, not "trust me bro"-reviewed)
6. **Lopez de Prado (2016)** - Hierarchical Risk Parity (yes, I read the whole thing. No, I don't recommend it at bedtime)

---

## Contributing

PRs welcome. If your contribution includes:
- Actual math: Merged instantly
- "Add AI-powered blockchain signals": Blocked permanently
- Bug fixes: You're a hero
- "Add NFT integration": Please seek help

---

## License

MIT - Because unlike trading gurus, I believe knowledge should be free.

---

<p align="center">
  <i>Built with sleep deprivation, caffeine, and the unshakeable belief that a robot can trade better than someone who draws lines on charts for a living.</i>
</p>

<p align="center">
  <b>If this repo made you exhale through your nose, star it. It's the least you can do after all the free alpha I just gave you.</b>
</p>
