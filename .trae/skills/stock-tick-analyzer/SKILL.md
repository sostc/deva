---
name: "stock-tick-analyzer"
description: "Analyze stock tick data for trading insights and pattern recognition. Use when users need to process, analyze, and derive insights from stock tick data."
---

# Stock Tick Data Analyzer

A skill for analyzing stock tick data to derive trading insights and identify patterns.

## Overview

This skill provides tools and methodologies for analyzing stock tick data, which is the most granular level of market data containing every trade and quote executed for a security.

## Core Features

### Data Processing
- **Tick Data Parsing:** Process raw tick data from various sources
- **Data Cleaning:** Remove outliers, handle missing values, and normalize data
- **Time Series Processing:** Convert tick data into different timeframes (1min, 5min, 15min, etc.)

### Analysis Techniques
- **Price Action Analysis:** Identify support/resistance levels, trends, and patterns
- **Volume Analysis:** Analyze trading volume patterns and their relationship with price movements
- **Market Depth Analysis:** Examine order book dynamics and liquidity
- **Statistical Analysis:** Calculate key metrics like volatility, spread, and tick imbalance

### Pattern Recognition
- **Intraday Patterns:** Identify common intraday patterns like morning gap, lunchtime lull, and end-of-day action
- **Reversal Patterns:** Detect potential trend reversals based on tick data patterns
- **Momentum Patterns:** Identify momentum shifts and continuation patterns

### Visualization
- **Tick Charts:** Create detailed tick charts for precise analysis
- **Volume Profiles:** Visualize volume distribution at different price levels
- **Time and Sales:** Display real-time or historical time and sales data

## Usage Guidelines

1. **Data Preparation:** Ensure tick data is in a standardized format with timestamps, price, volume, and other relevant fields
2. **Analysis Selection:** Choose appropriate analysis techniques based on your trading strategy and time horizon
3. **Pattern Identification:** Use the skill to identify meaningful patterns in the tick data
4. **Insight Generation:** Derive actionable trading insights from the analysis results
5. **Backtesting:** Test identified patterns against historical data to validate their effectiveness

## Best Practices

- **Data Quality:** Ensure high-quality tick data with minimal gaps and accurate timestamps
- **Computational Efficiency:** Process tick data efficiently, especially for large datasets
- **Contextual Analysis:** Consider market context and news events when interpreting tick data patterns
- **Risk Management:** Use tick data analysis as part of a comprehensive risk management strategy

## Examples

### Example 1: Intraday Momentum Analysis
**Input:** "Analyze tick data for AAPL to identify intraday momentum shifts"
**Output:** "Identified 3 significant momentum shifts in AAPL tick data today. The first occurred at 10:15 AM with a volume surge of 2.5x average, followed by a price increase of 0.8%."

### Example 2: Support/Resistance Identification
**Input:** "Find key support and resistance levels for MSFT using tick data"
**Output:** "Based on tick data analysis, MSFT has strong support at $345.20 (tested 4 times today) and resistance at $348.75 (rejected 3 times in the last 2 hours)."

### Example 3: Liquidity Analysis
**Input:** "Analyze market depth for GOOGL to assess liquidity"
**Output:** "GOOGL shows strong liquidity with an average bid-ask spread of 0.02% and depth of 1,200 shares at the best bid/ask levels."

## Conclusion

The Stock Tick Data Analyzer skill provides comprehensive tools for analyzing the most granular level of market data, enabling traders and investors to gain deeper insights into market dynamics and make more informed trading decisions.