# JSON Schemas

This document defines the JSON schemas used by the skill-creator.

## evals.json

```json
{
  "skill_name": "string",
  "evals": [
    {
      "id": "integer",
      "prompt": "string",
      "expected_output": "string",
      "files": ["string"],
      "assertions": [
        {
          "text": "string",
          "type": "string",
          "value": "string"
        }
      ]
    }
  ]
}
```

## eval_metadata.json

```json
{
  "eval_id": "integer",
  "eval_name": "string",
  "prompt": "string",
  "assertions": [
    {
      "text": "string",
      "type": "string",
      "value": "string"
    }
  ]
}
```

## timing.json

```json
{
  "total_tokens": "integer",
  "duration_ms": "integer",
  "total_duration_seconds": "number"
}
```

## grading.json

```json
{
  "expectations": [
    {
      "text": "string",
      "passed": "boolean",
      "evidence": "string"
    }
  ]
}
```

## benchmark.json

```json
{
  "skill_name": "string",
  "summary": [
    {
      "config": "string",
      "mean_time": "number",
      "std_time": "number",
      "mean_tokens": "number",
      "std_tokens": "number",
      "mean_pass_rate": "number",
      "std_pass_rate": "number"
    }
  ],
  "raw_data": {
    "(eval_name, config)": {
      "time": "number",
      "tokens": "number",
      "passes": "string"
    }
  }
}
```

## feedback.json

```json
{
  "reviews": [
    {
      "run_id": "string",
      "feedback": "string",
      "timestamp": "string"
    }
  ],
  "status": "string"
}
```
