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

Then I did what any sane person would do: I mass-pasted every single thing I learned into Claude and mass-spammed "make more money" until a trading bot came out the other side.

**I have not written a single line of code in this repository.** Not one. I don't know what half these files do. I opened `factor_composite.py` once and immediately closed it. There's a file called `kelly_sizing.py` and I genuinely don't know who Kelly is. There are 2,000+ lines in `auto_trader.py` and I have read exactly zero of them.

My entire contribution to this project is:
1. Mass-buying trading courses
2. Copy-pasting course content into an AI
3. Typing "make more money" repeatedly
4. Crying about token costs
5. Typing "make more money" again

**The AI wrote everything. I just mass-funded it.** My Claude API bill is now competing with my course spending for "worst financial decision." At least the courses came with a PDF. Claude just gives me a spinning cursor and hope.

**You're welcome.**

---

## How This Repo Gets Made

```
Me:     "make more money"
Claude: *writes 400 lines of quantitative finance code*
Me:     "is it working?"
Claude: "here's a detailed analysis of the Sharpe ratio and—"
Me:     "but is number going up"
Claude: *sighs in tokens*

[3 hours later]

Me:     "make MORE money"
Claude: *rewrites the entire risk management system*
Me:     "I don't know what any of this means but ship it"
Claude: "that'll be 50,000 tokens"
Me:     "...make more money but cheaper"
```

My token bill last month was higher than my trading profits. The AI is literally the only one making money here, and it's making it from ME.

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
**Total spent on Claude tokens to build this: I don't want to talk about it**

---

## The Strategies

### Factor Composite
Combines Momentum, Quality, Low Volatility, and Value factors. I don't know what any of those words mean individually, let alone combined. I just know 4 separate courses charged $2K+ each to teach ONE factor. The AI put all four in one file. I assume the instructors would be furious if they could read Python. I also cannot read Python.

### Simple Momentum
"Number go up, I buy. Number go down, I sell." That's literally it. That's the $4,999 course. You just saved $4,999 reading this line. You're welcome. This is actually the only strategy I understand.

### Pairs Trading
Statistical arbitrage. The course called it "Institutional-Grade Market Neutral Alpha Generation." The AI calls it "cointegration analysis." I call it "these two stocks usually move together and right now they're not." We're all saying the same thing. Mine just has fewer syllables.

### Dual Momentum
Based on Antonacci (2013) - an actual published paper, not a TikTok with rocket emojis. The course that taught this charged $997 and added a proprietary indicator on top. The indicator was RSI. They charged $997 for RSI. I told Claude about this and I think it judged me.

### ML Momentum
Machine learning for trading. The course said "neural network." Claude says it's a gradient boosted tree. I don't know the difference. The course said "edge over Wall Street." It barely edges over a savings account. But at least our code runs. I think. I haven't checked.

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
   (because unlike your favorite guru, we believe in risk management)
7. Goes back to sleep
8. Repeats without checking Twitter for confirmation bias
9. I check my phone, see a number, feel an emotion, do nothing
```

---

## The Crypto Section

Since I know you're wondering: **No, this doesn't trade crypto.** Here's why:

| Stock Market | Crypto |
|-------------|--------|
| Opens at 9:30 AM, closes at 4 PM | Never closes. Your portfolio moves while you sleep. Why would anyone want this. |
| Regulated by the SEC | Regulated by vibes and a guy named "CZ" |
| Companies make actual products | "Utility token for a decentralized ecosystem" (it's a JPEG) |
| Dividends | "Staking rewards" (it's inflation with extra steps) |
| Warren Buffett | Some guy with laser eyes on Twitter |
| 10-K filings | A whitepaper written in Comic Sans |
| Market makers | A teenager in his mom's basement running a MEV bot |
| "Blue chip stocks" | "Blue chip NFTs" (they are neither blue nor chips) |
| Loses 20% in a crash | Loses 90% on a Tuesday. For fun. |
| Circuit breakers halt trading | Nothing halts trading. The suffering is 24/7/365. |
| My bot has stop losses | Crypto bros have "conviction" |
| Backed by earnings and assets | Backed by a Telegram group with 50,000 bots |

If you want to trade crypto, I respect your decision the same way I respect people who eat gas station sushi. Technically legal. Probably fine. But I'm not joining you.

**"But what about Bitcoin—"** Sir this is a stock trading bot.

**"Ethereum is basically—"** I can't hear you over the sound of my positions having stop losses.

**"Web3 will—"** Web3 will what? Replace the SEC with a DAO that votes on whether to rug pull? I'm good.

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
- **Correlation limits** - won't buy 5 tech stocks and call it "diversification"

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
| "WAGMI" | WAGMI (We Are Gonna Mass Impoverish) |
| "Few understand this" | Literally no one understands this, including me |
| "It's not a loss until you sell" | It's a loss. It's always been a loss. |
| "This is the way" | This is the way to bankruptcy court |
| "Decentralized" | No customer support when you get rugged |

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
| Developer | Claude (AI) | "World-class quant team" (it's one API call and a prayer) |
| Testing | pytest | Not taught in any course ever |
| My role | Typing "make more money" | "Visionary founder and CEO" |

---

## The Cost of Building This

| Expense | Amount | Was It Worth It |
|---------|--------|----------------|
| Trading courses | ~$47,000 | No |
| Claude API tokens | I'm not emotionally ready to check | Probably no |
| Alpaca paper trading | $0 | The only good financial decision I've made |
| My time | 500+ hours | I could have learned a real skill |
| My dignity | Gone | It left when I bought the TikTok guy's course |
| My sleep schedule | Destroyed | US market opens 4:30 PM my time. I live in South Africa. My life is a timezone nightmare. |
| Total ROI | Negative | But at least I have this README |

> "I mass-spent $47K on courses, mass-spent another fortune on AI tokens, and all I got was this mass-performing GitHub repo" - Me, at 3 AM, refreshing Alpaca

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

# 7. Refresh the page 47 times hoping the number changed
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
├── tests/               # We test our code. Gurus test nothing.
└── README.md            # The only file I actually wrote (with AI help)
```

---

## FAQ

**Q: Will this make me rich?**
A: It made me mass-buy trading courses, mass-burn API tokens, and mass-stare at charts at 3 AM. So no, but you'll be more educated than 99% of retail traders. Which is still poor, just smarter about it.

**Q: Did you really not write any code?**
A: I once tried to add a comment. It broke something. The AI fixed it in 0.3 seconds and I could feel its disappointment through the terminal. I have not touched a file since.

**Q: Is this financial advice?**
A: This is a GitHub repo built entirely by an AI, directed by someone who bought every trading course and is still not rich. Draw your own conclusions.

**Q: Why is it called "Vibe Vesting"?**
A: Because "I mass-funded the trading course industry then mass-spammed an AI with 'make more money' until a bot appeared" was too long for a repo name.

**Q: Can I use this for real money?**
A: You *can*. Should you? Ask yourself: "Would I trust a robot built at 3 AM by an AI taking orders from someone who's never read the code?" Exactly.

**Q: Why not just buy index funds?**
A: Because then I'd have nothing to do at 3 AM except make healthy life choices, and we don't do that here.

**Q: Do you have a Discord?**
A: No. And if I ever start one that costs $97/month, please stage an intervention. You have my full permission.

**Q: How much have you spent on tokens?**
A: Next question.

**Q: No seriously, how much?**
A: You know how people say "if you have to ask, you can't afford it"? I asked. I couldn't afford it. I did it anyway. This is consistent with every other financial decision I've made.

**Q: Is this better than crypto?**
A: My bot has stop losses, risk limits, and circuit breakers. Your favorite coin has a Telegram group run by an anonymous founder called "SatoshiKing69." We are not the same.

---

## Honest Disclaimer

This system trades with paper money. It has:
- Lost money
- Made money (occasionally, by accident, and never when I'm watching)
- Confused me
- Made me mass-check my portfolio at 3 AM
- Cost me more in AI tokens than it's made in trades
- Underperformed a simple index fund (we said we're honest)

The only guaranteed outcome of using this software is that you will learn nothing because you'll just tell an AI to "make more money" like I did. Whether you make money is between you, the AI, and the market gods.

---

## Academic References

Unlike your favorite trading influencer, we cite our sources. Not a single Telegram group or TikTok among them. I haven't read any of these. The AI has. I trust it. This is my investment strategy now.

1. **Jegadeesh & Titman (1993)** - Momentum (the OG, before TikTok traders discovered it)
2. **Fama & French (1993, 2015)** - Factor models (actual Nobel Prize-winning work, not "my proprietary system")
3. **Antonacci (2013)** - Dual Momentum (a real book with ISBN and everything)
4. **Kelly (1956)** - Position sizing (math, not vibes. Still don't know who Kelly is.)
5. **Kritzman et al. (2012)** - Regime detection (peer-reviewed, not "trust me bro"-reviewed)
6. **Lopez de Prado (2016)** - Hierarchical Risk Parity (the AI read this. I saw the title and took a nap.)

---

## Contributing

PRs welcome. If your contribution includes:
- Actual math: Merged instantly (by the AI, I won't understand it)
- "Add AI-powered blockchain signals": Blocked permanently
- Bug fixes: You're a hero and we'll name a variable after you
- "Add NFT integration": Please seek help
- "Integrate Dogecoin": Sir this is a Wendy's
- Better strategies: Only if they come with honest backtests, not screenshots of one good trade
- Token-efficient improvements: I will mass-merge these immediately. My wallet is begging you.

---

## License

MIT - Because unlike trading gurus, we believe knowledge should be free.

If someone tries to sell this code in a course, send them this link and tell them an AI gave it away for nothing, directed by someone who can't read Python.

---

<p align="center">
  <i>Built entirely by Claude. Directed by someone who mass-funded the entire trading course industry and is now mass-funding Anthropic's revenue.</i>
</p>

<p align="center">
  <b>I mass-bought every course. I mass-prompted an AI. I mass-spent tokens. And now you get it all for free. Star it out of spite.</b>
</p>

<p align="center">
  <sub>Total mass-spent on courses + tokens: more than I'll ever make trading. But hey, at least I have a really funny README.</sub>
</p>
