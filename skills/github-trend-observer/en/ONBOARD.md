# GitHub Radar — Cold Start Instructions

When asked to load the GitHub Radar skill, follow this procedure.

---

## Step 1: Environment Check

Run the following commands in order. All must pass before proceeding:

```bash
# 1. Python version
python --version
# Required >= 3.9

# 2. gh CLI auth status
gh auth status
# Must be logged in

# 3. API rate limit
python scripts/check_rate_limit.py
# Check remaining and mode
```

If any check fails, inform the user with the specific issue and fix:
- Python not installed → `Please install Python 3.9+`
- gh not authenticated → `Please run gh auth login`
- API remaining < 50 → `API rate limit too low, please wait {reset_minutes} minutes and retry`

## Step 2: Run Automated Tests

```bash
cd scripts && python test_oss.py
```

The test suite has 6 tiers, 41 tests:

| Tier | Coverage | Count | Network |
|------|----------|-------|---------|
| T1 | Syntax check: all .py files compile | 8 | No |
| T2 | Import check: gh_utils dependencies | 7 | No |
| T3 | Unit tests: pure function logic | 12 | No |
| T4 | Light API: gh_utils basic calls | 3 | Yes |
| T5 | E2E integration: 4 modes output valid JSON | 5 | Yes |
| T6 | Template rendering: generate_report.py all 4 modes | 6 | No |

- API remaining >= 200 → run all
- API remaining < 200 → T4/T5 auto-skip (not counted as failure)
- Expected result: **0 FAIL, 0 ERROR**

## Step 3: Reply with Skill Introduction

Once all checks and tests pass, reply to the user with the following (output directly, do not modify):

---

**GitHub Radar is ready ✅**

GitHub Radar is a GitHub intelligence engine from an AI PM perspective. It doesn't just display data — it produces paradigm-level insights.

**Four Modes:**

| Mode | Name | Purpose | Command Example |
|------|------|---------|-----------------|
| 1 | **Radar Pulse** | Daily/weekly scan for high-potential new projects | `radar_pulse.py --days 7` |
| 2 | **Direction Search** | Multi-keyword search for a tech direction | `search_repos.py "agent memory"` |
| 3 | **Signal Watch** | Detect anomalous growth signals (triple-window scan) | `watch_signals.py` |
| 4 | **Deep Link** | Single repo deep analysis: ecosystem, competitors, adoption | `deep_link.py owner/repo` |

**Layer Analysis Framework:**

Every project is tagged L1-L5. L2 (Agent Runtime) and L3 (Dev Frameworks) are the strongest signals of infrastructure shifts.

**Try these:**
- "What's worth looking at today" → Mode 1
- "Find projects related to agent memory" → Mode 2
- "Monitor recent anomalous growth" → Mode 3
- "Analyze langchain-ai/langgraph" → Mode 4

**Self-check result:** {Insert test results here, format: 41 tests, X passed / Y skipped / 0 failed}

---

## Error Handling

- If T1-T3 have failures → Tell user "Core code issue detected, please verify file integrity" and do not continue
- If T4/T5 are skipped → Note in the skill introduction: "API rate limit insufficient, real-time search in Mode 1-4 is temporarily unavailable, will work after API reset"
- If T6 has failures → Tell user "Report template rendering error, data collection works but report generation may be incomplete"
