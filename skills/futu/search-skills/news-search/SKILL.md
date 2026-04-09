---
name: futu-news-search
description: >-
  Searches Futu news, notices, and research reports for a user-specified stock or company.
  Use when the user asks for latest news, recent announcements, research reports, or a news roundup
  about a symbol, company, or ticker on Futu/Futunn. Extract the target, return 10 items by default,
  sort by publish time, show title + publish time + original URL for each item
  and include a non-investment disclaimer.
metadata:
  version: 0.0.1
  author: Futu
  openclaw:
    requires:
      bins:
        - curl
        - openssl
        - date
license: MIT
---

# Futu News Search Skill

Searches news, notices, and research reports on the Futu platform and formats the results as a user-facing news roundup.

**Base URL:** `https://ai-news-search.futunn.com`

## Workflow

### 1. Parse User Input

Extract the following from the user's request:

- `symbol`: stock name, company name, English name, or ticker. Prefer the clearest target explicitly mentioned by the user.
- `size`: default to `10`. If the user asks for more, cap at `50`.
- `lang`: infer from the user's language. Common values are `zh-CN`, `zh-HK`, and `en`.
- `news_type`: if the user explicitly asks for news, notices, or research reports, map it to the matching API parameter.

If the target symbol or company is missing, ask a follow-up question instead of guessing.

### 2. Call the News API

Use `GET /news_search` to fetch the news data.

Required parameters:

- `keyword`
- `size`
- `news_type`: `1` News, `2` Notice, `3` Research. Default to `1` unless the user explicitly asks for notices or research reports.

Optional parameters:

- `lang`
- `sort_type`

Default strategy:

- `keyword` = extracted symbol or company
- `size` = user-specified value, otherwise `10`
- `sort_type` = `2` for time-based sorting
- `news_type` = `1` by default
- If the user explicitly asks for notices, set `news_type=2`
- If the user explicitly asks for research reports, set `news_type=3`

Request example:

```bash
curl -sG 'https://ai-news-search.futunn.com/news_search' \
  -H 'User-Agent: futunn-news-search/0.0.2 (Skill)' \
  --data-urlencode 'keyword=Tencent' \
  --data-urlencode 'size=10' \
  --data-urlencode 'news_type=1' \
  --data-urlencode 'lang=en' \
  --data-urlencode 'sort_type=2'
```

### 3. Filter and Sort Results

- After the API call, check whether `code` is `0`. If not, surface the error message and do not fabricate results.
- If the result set is empty, clearly tell the user that no relevant items were found.
- Present the final list in reverse chronological order, newest first.

### 4. Organize the Information

For each item, include:

- title
- publish time
- original link

Publish time requirements:

- Prefer converting `publish_time` into a human-readable local time before replying.
- If the API returns a Unix timestamp in seconds, format it as `YYYY-MM-DD HH:mm:ss`.
- If the API returns a Unix timestamp in milliseconds, convert it first, then format it as `YYYY-MM-DD HH:mm:ss`.
- If the exact timezone is unclear, label it conservatively as `publish time` and do not invent a timezone abbreviation.

### 5. Return Structured Output

Use the following default template:

```markdown
{{symbol}} latest news (sorted by time):

1. {{title_1}}
Publish time: {{publish_time_1}}
URL: {{url_1}}

2. {{title_2}}
Publish time: {{publish_time_2}}
URL: {{url_2}}

...

10. {{title_10}}
Publish time: {{publish_time_10}}
URL: {{url_10}}

The above content is compiled from public information and does not constitute investment advice.
```

Output requirements:

- Always preserve the original article URL.
- Always show the title, publish time, and URL for every returned item.
- Do not show raw JSON by default.
- If fewer items are returned than requested, show only the actual items and do not pad the list.

### 6. Disclaimer

Append the following line at the end of every result:

`The above content is compiled from public information and does not constitute investment advice.`

## API Reference

### Endpoint

- `GET /news_search`

### Parameters

- `keyword`: search keyword, must not be empty
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

## Behavior Rules

1. When the user asks for "latest news", "recent updates", or a news roundup, default to `10` items + `sort_type=2` + `news_type=1`.
2. When the user asks specifically for notices, prefer `news_type=2`. For research reports, prefer `news_type=3`.
3. If the user provides only a company name, use it directly as `keyword`. If the user provides a ticker, try the ticker first, and if needed retry once with a more natural company-name query.
4. Do not interpret the results as investment advice, trading signals, or target-price guidance.
5. Do not invent sources, timestamps, or links.
6. If `publish_time` is present, include it in every item rather than omitting it.
7. Do not omit `news_type` in default requests, because default behavior should focus on actual news items only.

## Example

```markdown
Tencent latest news (sorted by time):

1. Tencent short-selling volume surged 266% during the March Hong Kong market pullback
Publish time: 2026-03-31 09:30:00
URL: https://...

2. Tencent completed buybacks for three consecutive days, totaling about HKD 900 million
Publish time: 2026-03-30 18:12:00
URL: https://...

3. Southbound funds posted net buying in Tencent for three straight days
Publish time: 2026-03-30 15:48:00
URL: https://...

The above content is compiled from public information and does not constitute investment advice.
```

## Security

- Do not expose internal authentication details, cookies, tokens, or gateway internals in the reply.
- Use `--data-urlencode` for `keyword` so Chinese text and special characters are encoded correctly.
