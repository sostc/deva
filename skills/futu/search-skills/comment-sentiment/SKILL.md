---
name: futu-comment-sentiment
description: >-
  Aggregates real-time Futu community/feed discussions for one or more user-specified
  symbols, filters low-quality posts, classifies sentiment as bullish, bearish,
  or neutral, and returns a structured community sentiment snapshot for a single
  stock or a multi-symbol portfolio. Use when the user asks for stock community
  sentiment, retail discussion tone, portfolio sentiment snapshot, bullish vs
  bearish discussion, or futu-comment-sentiment.
metadata:
  version: 0.0.2
  author: Futu
  openclaw:
    requires:
      bins:
        - curl
        - openssl
        - date
license: MIT
---

# Futu Comment Sentiment Skill

HTTP **single-symbol or multi-symbol real-time community sentiment aggregation** for discussions on the Futu platform.

This skill is designed for user requests such as:

- "Check NVDA community sentiment"
- "Is Tesla community sentiment bullish or bearish lately?"
- "Analyze the community sentiment for this group of stocks"
- "Create a community sentiment summary for my US tech portfolio"

The skill retrieves recent community posts for each target symbol, filters low-quality content, computes bullish / bearish / neutral distribution, then produces:

1. single-symbol sentiment output when only one target is supplied
2. portfolio-level sentiment summary when multiple targets are supplied
3. top community opinions across the whole group
4. per-symbol sentiment breakdown for comparison

**Base URL:** `https://ai-news-search.futunn.com`

---

## Positioning

This skill focuses on **community discussion tone**, not fundamental valuation, not official filings, and not price prediction.

It should be used when the user wants:

- retail discussion mood
- community consensus vs disagreement
- quick symbol-by-symbol sentiment comparison
- a structured portfolio sentiment snapshot

It is **not** a fit for:

- official announcements only
- pure news roundup without community interpretation
- financial advice, target price, or trading execution

---

## Workflow

### 1. Parse User Input

Extract the following from the user's request:

- `symbol_list`: one or more symbols, company names, or recognizable stock aliases
- `group_name`: optional portfolio/group display name if the user provides one, for example `US Tech Portfolio`
- `lang`: infer from the user's language, typically `zh-CN`, `zh-HK`, or `en`

Parsing rules:

1. If no symbol can be identified, ask the user to provide at least one target.
2. If only one symbol is identified, run **single-symbol mode**.
3. If multiple symbols are identified, run **multi-symbol mode**.
4. Ignore user-provided time windows unless the upstream API explicitly supports them, because this skill is defined as a real-time snapshot workflow.

### 2. Call Community Data API

For each symbol in `symbol_list`, retrieve recent discussion/feed posts related to that symbol.

Preferred retrieval strategy:

1. Use the Futu feed/community endpoint that returns recent stock-related discussion items.
2. Keep results in reverse chronological order.
3. Preserve upstream metadata per symbol.
4. If a symbol fails upstream, record the failure and continue processing other symbols instead of aborting the whole batch.

### 3. Information Processing

For each symbol separately:

1. Clean text:
   - strip HTML tags from title / desc
   - merge visible title + desc into one analysis text
2. Convert timestamps:
   - treat `publish_time` as a Unix epoch value (seconds); if it looks like milliseconds (> 1e12), divide by 1000
   - convert to a human-readable string in the format `YYYY-MM-DD HH:mm` using UTC+8 (Asia/Shanghai) unless the user's locale implies otherwise
   - store the converted string as `published_at` on each post
   - after processing all posts for a symbol, record `time_range_earliest` and `time_range_latest` from the full (pre-filter) batch so the header reflects the actual data window
3. Filter low-quality content:
   - remove spammy or near-empty text
   - remove obvious water posts / repeated filler phrases
   - down-weight or exclude posts with extremely weak information density
   - down-weight or exclude very low-interaction content when interaction signals are available
3. Classify each retained post:
   - `bullish`
   - `bearish`
   - `neutral`
4. Aggregate each symbol:
   - `bull_pct`
   - `bear_pct`
   - `neutral_pct`
   - `post_count`
5. Extract representative viewpoints:
   - prioritize concrete opinions, catalysts, concerns, valuation views, trading interpretations
   - avoid repetitive phrasing and low-information remarks

### 4. Aggregate Analysis

If only **1 symbol**:

- output that symbol's sentiment result directly
- generate one-line summary
- extract top `3` viewpoints for that symbol

If **multiple symbols**:

1. Compute **group-level sentiment** across all retained posts from all symbols.
2. Generate one-line **group summary**.
3. Identify whether group sentiment is driven by one or several symbols.
4. Then provide **per-symbol breakdown**.
5. Extract top `3` group-level viewpoints across the combined sample.

### 5. Organize the Information

The response should always include:

1. a headline with target/group name
2. sentiment percentages
3. total retained post count
4. a concise summary sentence
5. top viewpoints
6. disclaimer

### 6. Return Structured Result

Return a normalized object so downstream callers can reliably parse the result.

### 7. Append Disclaimer

Every user-facing answer must end with a non-investment disclaimer.

---

## Retrieval Parameters

### Required Logical Inputs

- `symbol_list`: array of one or more targets

### Optional Logical Inputs

- `group_name`: optional portfolio or group label
- `lang`: optional language hint
- `size_per_symbol`: optional retrieval count per symbol when the upstream API requires an explicit size; default `30`, clamp to `1-50`

### Validation Rules

| Check | Rule |
| ----- | ---- |
| `symbol_list` missing or empty | Reject and ask for at least one symbol. |
| empty symbol after trim | Drop it and note it internally. |
| duplicate symbols | Deduplicate while preserving original order. |
| `size_per_symbol` omitted | Default to `30`. |
| `size_per_symbol < 1` | Clamp to `1`. |
| `size_per_symbol > 50` | Clamp to `50` unless deployment allows more. |

---

## Upstream Data Contract

This skill assumes an upstream Futu discussion/feed endpoint similar to `stock_feed` or a community feed search endpoint that can retrieve recent stock-related posts.

Typical request shape:

```bash
curl -sG 'https://ai-news-search.futunn.com/stock_feed' \
  -H 'User-Agent: futunn-comment-sentiment/0.0.2 (Skill)' \
  --data-urlencode 'keyword=NVDA' \
  --data-urlencode 'size=30'
```

Common top-level response:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `code` | int32 | `0` means success |
| `message` | string | error message or empty string |
| `data` | array | list of feed/community items |

Common item fields:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `id` | string | unique post ID |
| `title` | string | post title |
| `desc` | string | post content or excerpt, may contain HTML |
| `publish_time` | string \| int64 | publish timestamp |
| `url` | string | optional deep link |

If the actual upstream endpoint exposes extra fields such as interaction count, likes, comments, or heat score, the agent should use them to improve low-quality filtering.

---

## Sentiment Classification Rules

Use only three labels at the **post level**:

- `bullish`
- `bearish`
- `neutral`

Use four labels at the **aggregate level** when needed:

- `bullish`
- `bearish`
- `neutral`
- `mixed`

### Bullish Cues

Examples:

- expectation of rise, rebound, breakout, upside
- confidence in earnings, product cycle, AI demand, orders, margin expansion
- supportive valuation discussion
- optimistic dip-buying or long-term holding rationale

### Bearish Cues

Examples:

- expectation of drop, retracement, weak outlook, demand softness
- concern about earnings miss, competition, regulation, dilution, delivery issues
- negative valuation view
- panic, capitulation, or strongly risk-off tone

### Neutral Cues

Examples:

- factual updates without directional opinion
- watch-and-see commentary
- mixed or ambiguous stance
- low-confidence content with no clear directional bias

### Mixed Aggregate Rule

If bullish and bearish shares are both meaningful and neither side has a clear edge, the aggregate result may use `mixed`.

Recommended rule:

- if `abs(bull_pct - bear_pct) < 15%`
- and both `bull_pct >= 25%` and `bear_pct >= 25%`
- aggregate label may be `mixed`

Otherwise:

- dominant bullish share -> `bullish`
- dominant bearish share -> `bearish`
- weak directional evidence -> `neutral`

---

## Low-Quality Filtering Rules

This step is mandatory. Do not treat every retrieved post equally.

### Filter Out Or Down-Weight

- extremely short filler content such as only emojis, only "buy", only "to the moon", only ticker repeats
- pure repost markers with no view
- obvious spam, ads, referral text, or off-topic content
- repetitive slogan-style content with no incremental information
- machine-like templated posts
- posts with extremely weak interaction when interaction signals are available

### Keep Preferentially

- posts with explicit directional view
- posts with concrete reasons, catalysts, or concerns
- posts with clear disagreement that explains why the market is split
- posts with meaningful interaction or recognizable discussion value

### Important Guardrail

If interaction fields are **not** available upstream, still perform text-quality filtering. Do not fabricate interaction-based thresholds.

---

## Group-Level Aggregation Rules

When multiple symbols are provided, follow this exact order:

1. complete per-symbol filtering and sentiment counting first
2. merge all retained posts across symbols into one combined sample
3. compute:
   - `group_bull_pct`
   - `group_bear_pct`
   - `group_neutral_pct`
   - `group_post_count`
4. generate one-line `group_summary`
5. identify which symbols contribute most to the current group tone
6. output per-symbol breakdown after the overall result

### Group Summary Style

Good examples:

- `Overall sentiment is bullish, with optimism driven mainly by NVDA while TSLA remains more divided.`
- `Portfolio sentiment is broadly neutral to cautious, with bearish opinions focused on demand and valuation pressure.`
- `Overall disagreement is significant: AAPL appears steadier, while TSLA and NVDA show more polarized views.`

Avoid:

- fake precision unsupported by the data
- strong causal claims about future price
- investment recommendations

---

## Hot Opinion Extraction Rules

Extract **Top 3** viewpoints from retained posts.

Requirements:

1. Use short user-style opinion summaries, preferably quotable.
2. Merge duplicate or near-duplicate opinions before ranking.
3. Prefer viewpoints that are:
   - repeated across multiple posts
   - specific and interpretable
   - representative of current mood
4. Avoid generic filler such as:
   - "still watching"
   - "wait and see"
   - "big moves today"
5. Sort the final top opinions by `published_at` descending (most recent first).

In multi-symbol mode:

- extract top `3` **group-level** opinions first
- optionally mention the driving symbol inside the summary if needed

---

## User-Facing Output Templates

### Single Symbol Template

```markdown
{{symbol}} Community Sentiment · Real Time
Data window: {{time_range_earliest}} ~ {{time_range_latest}}

Community:
Bullish {{bull_pct}}% · Bearish {{bear_pct}}% · Neutral {{neutral_pct}}%
(Based on {{post_count}} retained posts)

Summary:
{{summary}}

Top viewpoints:

1. "{{opinion_1}}" · {{opinion_1_time}}
2. "{{opinion_2}}" · {{opinion_2_time}}
3. "{{opinion_3}}" · {{opinion_3_time}}

This content is based on public information and does not constitute investment advice.
```

### Multi-Symbol Template

```markdown
{{group_name}} Community Sentiment · Real Time
Data window: {{time_range_earliest}} ~ {{time_range_latest}}

Overall community:
Bullish {{group_bull_pct}}% · Bearish {{group_bear_pct}}% · Neutral {{group_neutral_pct}}%
(Based on {{group_post_count}} retained posts)

Overall summary:
{{group_summary}}

Per-symbol sentiment:

- {{symbol_1}}: Bullish {{bull_pct_1}}% · Bearish {{bear_pct_1}}% · Neutral {{neutral_pct_1}}%
- {{symbol_2}}: Bullish {{bull_pct_2}}% · Bearish {{bear_pct_2}}% · Neutral {{neutral_pct_2}}%
- {{symbol_3}}: Bullish {{bull_pct_3}}% · Bearish {{bear_pct_3}}% · Neutral {{neutral_pct_3}}%

Top viewpoints:

1. "{{opinion_1}}" · {{opinion_1_time}}
2. "{{opinion_2}}" · {{opinion_2_time}}
3. "{{opinion_3}}" · {{opinion_3_time}}

This content is based on public information and does not constitute investment advice.
```

### Display Rules

1. If only one symbol is supplied, do not show group-level wrapper fields.
2. If fewer than `3` valid opinions exist, show only the actual number available.
3. If one symbol has too little valid data after filtering, explicitly say evidence is limited.
4. Never expose raw upstream IDs in normal user-facing output.
5. In English output, use `Bullish / Bearish / Neutral / Mixed` instead of localized labels.
6. Timestamp display format for `published_at` on opinions: `MM-DD HH:mm` (e.g., `04-01 19:45`). Omit the date part if all opinions are from today relative to `generated_at`.
7. The `Data window` header uses `MM-DD HH:mm` on both ends. If earliest and latest are on the same calendar day, the format may be shortened to `HH:mm ~ HH:mm` with the date shown once.

---

## Normalized Output Contract

Return one structured object with the following top-level fields:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `request` | object | effective request parameters |
| `generated_at` | string | ISO-8601 completion timestamp |
| `mode` | string | `single` or `multi` |
| `group` | object \| null | overall portfolio sentiment when `mode=multi` |
| `symbols` | array | per-symbol sentiment results |
| `top_opinions` | Opinion[] | top 3 overall opinions for user display |
| `disclaimer` | string | fixed disclaimer |

### `Opinion`

| Field | Type | Description |
| ----- | ---- | ----------- |
| `text` | string | opinion summary text |
| `published_at` | string | human-readable time string, `YYYY-MM-DD HH:mm` (UTC+8) |

### `request`

| Field | Type |
| ----- | ---- |
| `symbol_list` | string[] |
| `group_name` | string \| null |
| `lang` | string \| null |
| `size_per_symbol` | int32 |

### `group`

Only required when `mode=multi`.

| Field | Type | Description |
| ----- | ---- | ----------- |
| `label` | string | `bullish` / `bearish` / `neutral` / `mixed` |
| `bull_pct` | string | percentage string |
| `bear_pct` | string | percentage string |
| `neutral_pct` | string | percentage string |
| `post_count` | int32 | retained group post count |
| `summary` | string | one-line group summary |

### `symbols[]`

| Field | Type | Description |
| ----- | ---- | ----------- |
| `symbol` | string | target symbol |
| `status` | string | `ok` / `error` / `empty` |
| `upstream_code` | int32 | raw upstream status |
| `upstream_message` | string | raw upstream message |
| `label` | string | `bullish` / `bearish` / `neutral` / `mixed` |
| `bull_pct` | string | percentage string |
| `bear_pct` | string | percentage string |
| `neutral_pct` | string | percentage string |
| `post_count` | int32 | retained post count |
| `time_range` | object | `{ earliest: string, latest: string }` in `YYYY-MM-DD HH:mm` (UTC+8), derived from the full pre-filter batch |
| `summary` | string | one-line symbol summary |
| `top_opinions` | Opinion[] | top viewpoints for this symbol, each with `text` and `published_at` |
| `signals` | object | optional reasoning evidence |

### `symbols[].signals`

| Field | Type | Description |
| ----- | ---- | ----------- |
| `bullish_signals` | string[] | repeated positive cues |
| `bearish_signals` | string[] | repeated negative cues |
| `uncertainties` | string[] | weak evidence or ambiguity |

---

## Minimal JSON Example

```json
{
  "request": {
    "symbol_list": ["NVDA", "TSLA", "AAPL"],
    "group_name": "US Tech Portfolio",
    "lang": "en",
    "size_per_symbol": 30
  },
  "generated_at": "2026-04-01T10:00:00.000Z",
  "mode": "multi",
  "group": {
    "label": "bullish",
    "bull_pct": "61%",
    "bear_pct": "27%",
    "neutral_pct": "12%",
    "post_count": 842,
    "summary": "Overall sentiment is bullish, with optimism driven mainly by NVDA while TSLA remains more divided."
  },
  "symbols": [
    {
      "symbol": "NVDA",
      "status": "ok",
      "upstream_code": 0,
      "upstream_message": "",
      "label": "bullish",
      "bull_pct": "68%",
      "bear_pct": "22%",
      "neutral_pct": "10%",
      "post_count": 286,
      "time_range": { "earliest": "2026-04-01 17:32", "latest": "2026-04-01 19:57" },
      "summary": "Community sentiment is broadly bullish, with optimism centered on AI demand and earnings continuation.",
      "top_opinions": [
        { "text": "AI demand is still accelerating; this NVDA run may not be over yet.", "published_at": "2026-04-01 19:45" },
        { "text": "The pullback looks more like trading noise and does not break the mid-term thesis.", "published_at": "2026-04-01 18:51" },
        { "text": "Valuation is not cheap, but the fundamentals are still delivering.", "published_at": "2026-04-01 18:03" }
      ],
      "signals": {
        "bullish_signals": ["AI demand", "earnings momentum"],
        "bearish_signals": ["valuation concern"],
        "uncertainties": ["short-term momentum can reverse quickly"]
      }
    },
    {
      "symbol": "TSLA",
      "status": "ok",
      "upstream_code": 0,
      "upstream_message": "",
      "label": "mixed",
      "bull_pct": "49%",
      "bear_pct": "38%",
      "neutral_pct": "13%",
      "post_count": 301,
      "time_range": { "earliest": "2026-04-01 16:10", "latest": "2026-04-01 19:55" },
      "summary": "Bullish and bearish views are clearly split, with optimism coexisting alongside demand concerns.",
      "top_opinions": [
        { "text": "This TSLA move feels more like a sentiment rebound than a solid reset.", "published_at": "2026-04-01 19:30" },
        { "text": "The new narrative is still alive, but delivery pressure has not disappeared.", "published_at": "2026-04-01 18:22" },
        { "text": "If deliveries improve, sentiment could recover quickly.", "published_at": "2026-04-01 17:48" }
      ],
      "signals": {
        "bullish_signals": ["narrative rebound"],
        "bearish_signals": ["delivery pressure", "demand concern"],
        "uncertainties": ["opinion split is large"]
      }
    }
  ],
  "top_opinions": [
    { "text": "AI demand is still accelerating; this NVDA run may not be over yet.", "published_at": "2026-04-01 19:45" },
    { "text": "This TSLA move feels more like a sentiment rebound than a solid reset.", "published_at": "2026-04-01 19:30" },
    { "text": "Apple does not seem to have much incremental upside right now and looks more like a defensive allocation.", "published_at": "2026-04-01 18:10" }
  ],
  "disclaimer": "This content is based on public information and does not constitute investment advice."
}
```

---

## Behavior Rules

1. Always parse the request into `symbol_list` first. Do not reduce a portfolio request into a single-keyword task.
2. Always apply low-quality filtering before computing percentages.
3. Base conclusions on retrieved discussion text, not prior market knowledge.
4. If upstream fails for one symbol, keep the batch result and mark that symbol as failed.
5. If a symbol has too few valid posts after filtering, say evidence is limited instead of over-interpreting.
6. In multi-symbol mode, output the **group result first**, then per-symbol breakdown.
7. Hot opinions should be de-duplicated summaries, not raw copied spam.
8. Never provide buy/sell advice or imply certain future price direction.

---

## Authentication

- Public gateway usage typically does not require explicit API keys in the documented contract.
- If an internal deployment later adds authentication, use environment variables or secret storage and never hardcode secrets in this skill.

---

## Security

### Requests And Data

- Treat all symbols as user input and URL-encode them.
- Strip HTML before display.
- Avoid logging large raw post bodies when not needed.
- Do not expose internal gateway details, cookies, or secrets.

### Disclaimer

- Community sentiment is only a discussion-sample summary.
- Sentiment does not equal future price direction.
- Responses are informational only and not investment advice.

---

## User Agent Header

Include a `User-Agent` header with the following string: `futu-comment-sentiment/0.0.2 (Skill)`
