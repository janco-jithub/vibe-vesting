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

I bought every single trading course on the internet. All of them.

The $997 "Elite Trader Mentorship." The $2,997 "Inner Circle." The $47 ebook that was actually a PDF of someone's Robinhood screenshots. The FREE webinar that lasted 3 hours just to sell me a $4,999 upsell. The Discord that charged $497/month for "BUY AAPL" alerts. The guy on TikTok who said he turned $500 into $500K using "one weird trick." I even bought the $14.99 Udemy one during a sale.

**Total spent on courses: enough to have been profitable if I'd just bought SPY.**

But here's the thing. After consuming literally every course, every "strategy," every "secret indicator," every guru's "proprietary system"... I realized they all teach the same 4 things:

1. Buy when number go up
2. Sell when number go down
3. "Manage your risk" (never explained how)
4. Here's my referral link

So I did what any sane person would do after mass-funding the entire trading education industrial complex: **I put every single thing I learned into one Python bot.**

This is the Infinity Gauntlet of trading courses. Every strategy. Every indicator. Every risk management technique. Every academic paper they plagiarized. All compressed into code that actually runs instead of a 47-slide PowerPoint with stock photos of Lamborghinis.

**You're welcome.**

---

## What's Inside (aka $47,000 worth of courses, free)

| Feature | Which Course Taught This | What They Charged | Our Price |
|---------|--------------------------|-------------------|-----------|
| Multi-Factor Strategy | "The Quant Edge Masterclass" | $2,997 | $0 |
| Kelly Position Sizing | "Advanced Options Bootcamp" | $1,497 | $0 |
| VIX Regime Detection | "Market Wizard Secrets" (it wasn't a secret) | $997 | $0 |
| Trailing Stop Losses | "Risk Mastery Academy" | $497/mo | $0 |
| Circuit Breakers | Nobody teaches this because they want you to blow up and buy the course again | $0 (they don't teach it) | $0 |
| Momentum Trading | 47 different YouTube channels simultaneously | $0 (but 200 hours of my life) | $0 |
| Pairs Trading | "Hedge Fund Strategies Revealed" (narrator: they were not hedge fund strategies) | $1,997 | $0 |
| Machine Learning Signals | "AI Trading Bot Masterclass" (it was a linear regression) | $3,997 | $0 |

**Total value according to gurus: $47,000+**
**Total value according to our backtest: about the same as buying SPY and going outside**

---

## The Strategies

### Factor Composite
Combines Momentum, Quality, Low Volatility, and Value factors. Taken from 4 separate courses that each charged $2K+ to teach ONE factor. We put all four in one file. The instructors would be furious if they could read Python.

### Simple Momentum
"Number go up, I buy. Number go down, I sell." That's literally it. That's the $4,999 course. You just saved $4,999 reading this line. You're welcome.

### Pairs Trading
Statistical arbitrage. The course called it "Institutional-Grade Market Neutral Alpha Generation." We call it "these two stocks usually move together and right now they're not." Same thing. Theirs just had more syllables.

### Dual Momentum
Based on Antonacci (2013) - an actual published paper, not a TikTok with rocket emojis. The course that taught this charged $997 and added a proprietary indicator on top. The indicator was RSI. They charged $997 for RSI.

### ML Momentum
Machine learning for trading. The course said "neural network." It's a gradient boosted tree. The course said "real-time predictions." It runs once every 5 minutes. The course said "edge over Wall Street." It barely edges over a savings account. But at least our code runs.

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
8. Repeats without checking Twitter for confirmation bias
```

---

## Risk Management

> "Risk management? Where we're going, we don't need risk management"
> \- Every blown-up account ever

This is the section that NO course teaches properly because managing risk doesn't have a referral link.

- **2% daily loss limit** - because drawdowns are not a "buying opportunity," they're a warning
- **15% max drawdown halt** - the machine literally turns itself off before going full WSB
- **Position sizing** - max 20% per trade, not "mortgage the house on TSLA weeklies"
- **Circuit breakers** - inspired by the stock exchange, not your uncle's "diamond hands" strategy
- **VIX monitoring** - when fear is high, we get small. When your guru says "blood in the streets," we're already out
- **Trailing stops that don't reset** - we literally had a bug where trailing stops reset every 5 minutes. Course value: $0. Bug fix value: priceless.

---

## Performance

Let's be honest about backtests. Here's what the system *actually* did (2021-2026, $100K starting capital), not what I cherry-picked to sell you a course:

| Strategy | Return | Sharpe | Max DD | Win Rate | Guru Equivalent |
|----------|--------|--------|--------|----------|-----------------|
| Factor Composite | +26% | 0.18 | -43% | 38% | "$2,997 mentorship" |
| Simple Momentum | +9.5% | -0.20 | -15% | 32% | "FREE signals group" |
| SPY Buy & Hold | +85% | ~1.0 | -25% | N/A | "Just buy the index bro" |

**Yes, SPY beat both strategies.** You know what that means? It means we're honest. Unlike the guy on YouTube who backtested to 2009 and said "if you invested $1,000 you'd have $47 million."

Every trading course shows you the ONE backtest that worked. We're showing you the ones that didn't. This is called "integrity" and it's why we'll never sell a course.

### Bugs We Found and Fixed (the real alpha)

| Bug | Impact | Status |
|-----|--------|--------|
| VIX multiplier applied TWICE | Positions 56% smaller than intended. $97K sitting as cash like a boomer savings account. | Fixed |
| Quality score always = 0.40 | 25% of our best strategy literally doing nothing for months | Fixed |
| Pyramiding needs 300% gain | Compared 0.03 with >= 3.0 (off by 100x). Not even NVDA does that in a week. | Fixed |
| Trailing stops reset every 5 min | Canceled and re-placed each cycle, losing high-water mark. Self-sabotage speedrun. | Fixed |
| Kelly sizing used fantasy stats | Thought win rate was 55% when actual is 34%. Aspirational math. | Fixed |
| Signal processor only checked 5 signals | Mixed BUY/SELL in one list, existing positions consumed all slots. $74K cash sat idle while the bot kept trying to buy stocks it already owned. Like applying to a job you already have. | Fixed |

> "The real alpha was the bugs we fixed along the way" - Warren Buffett, probably

---

## The Trading Guru Translation Guide

For when you're watching YouTube at 2 AM and need a reality check:

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
| "Technical Analysis" | Astrology for finance bros |
| "My proprietary indicator" | It's RSI with a different color |
| "Join my inner circle" | Pyramid scheme with candlestick charts |
| "Limited spots available" | There's no limit. It's a Gumroad link. |

---

## Tech Stack

| Component | Technology | Guru Equivalent |
|-----------|------------|-----------------|
| Backend | Python | "My system uses proprietary AI" (it's an if-statement) |
| Data | Alpaca API | "I have insider connections" (it's a free API) |
| Database | SQLite | "Cloud-based infrastructure" (it's a file) |
| Frontend | React + Tailwind | "Custom dashboard worth $50K" (it's a div with CSS) |
| ML Model | LightGBM | "Neural network AI" (it's gradient boosting) |
| Execution | Alpaca Paper Trading | "Live trading with millions" (it's fake money) |
| Testing | pytest | Not taught in any course ever |

---

## Quick Start

```bash
# 1. Clone (it's free, unlike everything else in trading)
git clone https://github.com/janco-jithub/vibe-vesting.git
cd vibe-vesting

# 2. Install dependencies (cheaper than a Discord subscription)
pip install -r requirements.txt

# 3. Set up your .env (keep your keys secret, unlike crypto influencers)
cp .env.example .env
# Edit .env with your Alpaca API keys (free at alpaca.markets)

# 4. Download historical data (for backtesting, not for hindsight trading)
python -m scripts.backfill_historical --symbols SPY,QQQ,TLT,AAPL,GOOGL --days 365

# 5. Let the robot do what you can't: trade without emotions
python -m scripts.auto_trader --strategies factor_composite simple_momentum

# 6. Watch the dashboard and pretend you understand what's happening
./scripts/start_dashboard.sh

# 7. Check your positions and feel something
python -m scripts.run_paper_trading --check-only
```

---

## Project Structure

```
vibe-vesting/
├── strategies/          # $47K worth of courses (free)
├── risk/                # What every course skips
├── execution/           # Robot go brrr
├── data/                # Numbers (real ones, not screenshots)
├── backtest/            # Where guru claims go to die
├── monitoring/          # Making sure the robot hasn't gone rogue
├── frontend/            # Pretty charts to cope with losses
├── scripts/             # Press button, receive trades
└── tests/               # We test our code. Gurus test nothing.
```

---

## FAQ

**Q: Will this make me rich?**
A: It made me mass-buy trading courses, mass-read academic papers, mass-write Python code, and mass-stare at charts at 3 AM. So no, but you'll be more educated than 99% of retail traders. Which is still poor, just smarter about it.

**Q: Is this financial advice?**
A: This is a GitHub repo written by someone who bought every trading course and is still not rich. Draw your own conclusions.

**Q: Why is it called "Vibe Vesting"?**
A: Because "I automated everything from $47K worth of courses and it still underperforms SPY" was too long for a repo name.

**Q: Can I use this for real money?**
A: You *can*. Should you? Ask yourself: "Would I trust a robot built at 3 AM by someone who's bought 30 trading courses to manage my life savings?" Exactly.

**Q: Why not just buy index funds?**
A: Because then I'd have nothing to do at 3 AM except make healthy life choices, and we don't do that here.

**Q: What's your Sharpe ratio?**
A: Higher than zero but lower than what any guru claims. So, realistic. We'd show you theirs for comparison but they've never actually calculated one.

**Q: Do you have a Discord?**
A: No. And if I ever start one that costs $97/month, please stage an intervention. You have my full permission.

**Q: Is this better than [guru name]'s strategy?**
A: We open-sourced our code, our backtest results, our bugs, and our losses. They open-sourced a Gumroad link. You tell me.

---

## Honest Disclaimer

This system trades with paper money. It has:
- Lost money
- Made money
- Confused me
- Made me mass-check my portfolio at 3 AM
- Taught me more than every course combined
- Underperformed a simple index fund (we said we're honest)

The only guaranteed outcome of using this software is that you will learn Python and never look at a trading guru the same way again. Whether you make money is between you and the market gods.

---

## Academic References

Unlike your favorite trading influencer, we cite our sources. Not a single Telegram group or TikTok among them:

1. **Jegadeesh & Titman (1993)** - Momentum (the OG, before TikTok traders discovered it)
2. **Fama & French (1993, 2015)** - Factor models (actual Nobel Prize-winning work, not "my proprietary system")
3. **Antonacci (2013)** - Dual Momentum (a real book with ISBN and everything)
4. **Kelly (1956)** - Position sizing (math, not vibes)
5. **Kritzman et al. (2012)** - Regime detection (peer-reviewed, not "trust me bro"-reviewed)
6. **Lopez de Prado (2016)** - Hierarchical Risk Parity (yes, I read the whole thing. No, I don't recommend it at bedtime. Yes, a course charged $997 to summarize it badly.)

---

## Contributing

PRs welcome. If your contribution includes:
- Actual math: Merged instantly
- "Add AI-powered blockchain signals": Blocked permanently
- Bug fixes: You're a hero and we'll name a variable after you
- "Add NFT integration": Please seek help
- Better strategies: Only if they come with honest backtests, not screenshots of one good trade

---

## License

MIT - Because unlike trading gurus, I believe knowledge should be free.

If someone tries to sell this code in a course, send them this link and tell them we already gave it away for nothing.

---

<p align="center">
  <i>Built by someone who mass-funded the entire trading course industry so you don't have to.</i>
</p>

<p align="center">
  <b>This repo contains more actual trading knowledge than every course I bought combined. And it's free. Star it out of spite.</b>
</p>
