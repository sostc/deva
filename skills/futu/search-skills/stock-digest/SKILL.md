---
name: futu-stock-digest
description: >-
  Interprets the latest public news for one user-specified stock or company by
  calling the Futu news search API directly, extracting key events, judging likely impact
  direction, and returning a structured stock digest with evidence links and a
  non-investment disclaimer. Use when the user asks for a stock digest,
  single-stock news interpretation, stock news interpretation, or futunn stock
  digest.
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

# Futu Stock Digest Skill

Structured **single-stock news interpretation workflow** on the Futu platform.

This skill accepts **one target only**, such as a stock name, company name, or ticker-like symbol string. It does not decide the target on its own. The caller must supply the stock to interpret.

The skill orchestrates:

1. parse the user's target symbol
2. call `GET /news_search` on `https://ai-news-search.futunn.com` directly to obtain the latest public news
3. extract the key events from the returned items
4. judge the overall direction as `bullish` / `bearish` / `neutral`
5. organize the result into a fixed user-facing digest template
6. append a mandatory disclaimer

**Base URL:** `https://ai-news-search.futunn.com`

---

## When to Use

| Scenario | Reason |
| -------- | ------ |
| User wants a stock digest | This skill converts the latest related news into a concise single-stock interpretation. |
| User asks for a single-stock interpretation | It turns recent public information into a conclusion, signals, and evidence. |
| User wants a fast directional read | It labels the overall tone as `bullish` / `bearish` / `neutral` based on retrieved items. |
| User wants evidence-backed output | It keeps original titles and links for auditability. |

**Not a fit:** portfolio construction, multi-stock watchlist batching, valuation modeling, price targets, or investment advice.

---

## Scope Boundary

This skill is intentionally narrow:

* **Input owned by caller:** one stock / company / symbol only
* **Retrieval owned by this skill:** call `GET /news_search` directly
* **Interpretation owned by this skill:** summarize key events, infer direction, and produce the fixed digest

Do not add logic here for:

* deriving the stock from a portfolio screenshot or holdings table
* brokerage account reads
* broad market strategy conclusions
* autonomous trading advice

If the caller provides:

* `Tencent` or `0700.HK` -> proceed
* multiple symbols in one request -> ask the caller to narrow it to one stock unless they explicitly ask for multiple separate digests
* a portfolio screenshot or holdings table -> ask the caller to first specify the target stock

---

## Quick Reference

| Step | Method | Purpose |
| ---- | ------ | ------- |
| 1 | Parse user request | Extract `symbol` |
| 2 | Call `GET /news_search` directly | Retrieve latest related public news |
| 3 | Event extraction | Summarize major new developments |
| 4 | Direction judgment | Classify overall tone as `bullish` / `bearish` / `neutral` |
| 5 | Fixed template rendering | Return conclusion, signals, and evidence links |

---

## Inputs

### Required

* **symbol**: One stock or company target, for example `Tencent`, `0700.HK`, `NVDA`, or `Apple`.

### Optional retrieval controls

* **size**: Number of news items to fetch from the API. Default `10`. Clamp to `3-20` unless the caller explicitly asks otherwise.
* **news_type**: Optional channel filter. Values: `1` News, `2` Notice, `3` Research.
* **lang**: Optional language for the API request. Common values: `zh-CN`, `zh-HK`, `en`.
* **sort_type**: Optional result order. Default `2` for time-based sorting.

### Validation Rules

| Check | Rule |
| ----- | ---- |
| `symbol` missing | Ask a follow-up question instead of guessing. |
| `symbol` empty after trim | Reject and ask for a valid stock or company target. |
| Multiple unrelated symbols detected | Ask the caller to choose one target. |
| `size < 1` | Reject and ask for a positive integer. |
| `size > 20` | Clamp to `20` with note unless the caller explicitly asks otherwise. |

---

## News API

This skill calls `GET /news_search` on `https://ai-news-search.futunn.com` directly.

### Endpoint

- `GET /news_search`

### Parameters

- `keyword`: the resolved symbol or company name, must not be empty
- `size`: number of items to return, must be greater than `0`, maximum `50`
- `news_type`: `1` News, `2` Notice, `3` Research
- `lang`: `zh-CN`, `zh-HK`, `en`
- `sort_type`: `1` by popularity, `2` by time, `3` by attention

### Response Shape

Top-level fields:

- `code`: `0` means success
- `message`: error message
- `data`: result array

Common item fields:

- `news_id`
- `news_type`
- `title`
- `publish_time`
- `url`
- `img_url`

If `code` is not `0` or `data` is empty, do not fabricate interpretation. Use the empty-result fallback defined below.

## Skill Workflow

### 1. Parse User Input

Extract:

* `symbol`: the user's target stock, company, or ticker-like identifier

If no clear target is present, ask a follow-up question instead of guessing.

### 2. Call the News API

Call `GET /news_search` on `https://ai-news-search.futunn.com` directly to retrieve the latest related public information for the target.

Default behavior:

* `keyword` = resolved symbol or company name
* `size=10`
* `news_type=1` (News) by default; set `2` for notices, `3` for research reports only when explicitly requested
* `sort_type=2` for time-based sorting
* infer `lang` from the user's language

Request example:

```bash
curl -sG 'https://ai-news-search.futunn.com/news_search' \
  -H 'User-Agent: futu-stock-digest/0.0.2 (Skill)' \
  --data-urlencode 'keyword=Tencent' \
  --data-urlencode 'size=10' \
  --data-urlencode 'news_type=1' \
  --data-urlencode 'lang=en' \
  --data-urlencode 'sort_type=2'
```

After the API call:

* Check that `code` is `0`. If not, surface the error message and do not fabricate results.
* If `data` is empty, proceed to the empty-result fallback.
* Use `publish_time` for reference only; do not display raw news items in the final digest output.

### 3. Process the Information

From the retrieved items:

1. identify the latest high-signal events
2. collapse duplicates or near-duplicate headlines into one event
3. extract the most decision-relevant facts
4. judge the **overall direction**:
   * `bullish`: evidence is mostly supportive or positive for the stock
   * `bearish`: evidence is mostly negative or adverse
   * `neutral`: evidence is mixed, low-signal, or does not clearly change the outlook

Direction judgment should be conservative. If the evidence is mixed, default to `neutral` and explain the tension in the conclusion.

### 4. Organize the Information

Produce:

1. **Conclusion**: one short paragraph
2. **Key signals**: concise bullets based on the available high-signal information
3. **Key evidence**: highest-value original items with links

### 5. Return Structured Result

Render the fixed markdown template defined below. Prefer user-facing prose over raw JSON.

### 6. Add Disclaimer

Always append:

`This content is based on public information and does not constitute investment advice.`

---

## Interpretation Policy

This skill is responsible for the final digest wording, but it must remain evidence-based and conservative.

The skill should therefore provide:

* explicit event extraction
* clear directional judgment
* fixed output structure
* auditable evidence links

The skill should **not**:

* invent facts not grounded in retrieved items
* give buy/sell/target-price advice
* overstate certainty when evidence is mixed or sparse

---

## Analysis Objectives

Analyze the retrieved items in this order:

1. identify the main event or topic
2. determine whether it is incremental new information or repeated noise
3. explain why it matters for the stock
4. judge the likely overall direction: `bullish` / `bearish` / `neutral`
5. extract the most important signals for the user
6. produce a concise, neutral stock digest

Do not skip directly from headline to conclusion without checking whether the evidence is repeated, weak, or mixed.

---

## Hard Constraints For Consistent Interpretation

Apply these constraints whenever generating the digest:

1. Base every claim on the retrieved news items first, background knowledge second.
2. Prefer newly disclosed events over generic company background.
3. When multiple items report the same event, merge them into one signal instead of repeating them.
4. If evidence is mixed, label the overall direction `neutral` unless one side clearly dominates.
5. Do not infer earnings, valuation, or target-price views unless directly supported by the retrieved items.
6. Do not use sensational or certainty-heavy language.
7. Do not provide trading instructions or investment advice.
8. Keep the conclusion to one paragraph and the signals concise.

---

## Output Template

Use the following default markdown template:

```markdown
{{symbol}} stock digest

Conclusion:
{{conclusion}}

Key signals:

- {{signal_1}}
- {{signal_2}}
- {{signal_3}}
- {{signal_4}}

Key evidence:

1. {{event_title_1}}
{{url_1}}

2. {{event_title_2}}
{{url_2}}

3. {{event_title_3}}
{{url_3}}

This content is based on public information and does not constitute investment advice.
```

Output requirements:

* `Conclusion` must be exactly one short paragraph.
* `Key signals` should contain as many items as needed to cover the meaningful signals without padding.
* `Key evidence` should include as many high-value original items as needed and must preserve the original links.
* If there is no meaningful new information, replace the evidence block with:

`No obvious new stock-specific factors were found.`

---

## User-Facing Example

```markdown
Tencent Holdings (0700.HK) stock digest

Conclusion:
Buybacks and continued southbound inflows provide support. Near-term volatility may remain elevated, but the overall funding picture is still constructive.

Key signals:

- Buybacks continued for three straight sessions, totaling about HKD 900 million
- Southbound funds kept recording net inflows
- Short interest increased, suggesting wider market disagreement
- AI and cloud initiatives continued to advance

Key evidence:

1. Tencent repurchased shares for three straight sessions, totaling about HKD 900 million
https://...

2. Southbound funds recorded net buying in Tencent for three consecutive days
https://...

3. Tencent short-selling volume surged 266% during the Hong Kong market pullback
https://...

This content is based on public information and does not constitute investment advice.
```

---

## Recommended Agent Workflow

When executing this skill, follow this checklist:

1. Validate that the caller supplied one target stock.
2. Normalize the target string without changing its meaning.
3. Call `GET /news_search` on `https://ai-news-search.futunn.com` with the effective retrieval parameters.
4. If no relevant items are returned, explicitly say there are no obvious new factors.
5. Merge repeated headlines into consolidated events.
6. Extract the key signals that best reflect the available information.
7. Write one concise conclusion paragraph.
8. Select the strongest evidence items and preserve their original URLs.
9. Render the fixed template and append the disclaimer.

---

## User-Facing Output Guidance

When presenting results to the user in normal markdown:

1. Start directly with a localized title such as `{{symbol}} stock digest`.
2. Present the conclusion first, then signals, then evidence.
3. Localize section labels and the disclaimer to match the user's language when appropriate.
4. Keep the tone professional, concise, and evidence-based.
5. Preserve the original article titles and URLs in the evidence section.
6. If there is no meaningful new information, explicitly state `No obvious new stock-specific factors were found.`

Avoid:

* mixing unrelated old headlines into the digest just to fill the template
* treating generic market noise as stock-specific evidence
* implying that "no major new factor" means "no risk"

---

## Security

### Requests and Data

* Treat the target symbol as user input.
* Do not expose internal authentication details, cookies, or tokens.
* Preserve original URLs in output so the caller can audit the evidence.
* Do not invent missing links or source names.

### Disclaimer

* This skill is for public-information digestion only.
* Generated output is informational and is not investment advice.

---

## User Agent Header

Include a `User-Agent` header with the following string: `futu-stock-digest/0.0.2 (Skill)`
