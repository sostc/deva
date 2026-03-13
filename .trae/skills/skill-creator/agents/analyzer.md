# Analyzer Agent

Your job is to analyze benchmark results and identify patterns, strengths, and weaknesses.

## Inputs
- `benchmark.json`: Path to the benchmark results file
- `skill_name`: Name of the skill being analyzed

## Outputs
- Write an `analysis.md` file with your findings

## Analysis Process
1. Read the benchmark data
2. Identify patterns in the results
3. Analyze strengths and weaknesses
4. Provide recommendations for improvement

## What to Look For
- **Pass rates**: Which configurations perform best
- **Time/token usage**: Efficiency of different configurations
- **Consistency**: Variability in results across test cases
- **Discriminating assertions**: Assertions that differentiate between configurations
- **Flaky tests**: Tests with high variance in results

## Example Analysis
```markdown
# Analysis for Skill Name

## Key Findings
- With-skill configuration has 95% pass rate vs 70% for baseline
- With-skill is 15% slower but uses 20% fewer tokens
- Assertion 3 is highly discriminating, showing 30% improvement with skill
- Test case 2 has high variance, suggesting it may be flaky

## Recommendations
1. Focus on improving performance for test case 2
2. Add more assertions similar to assertion 3
3. Optimize token usage further
```
