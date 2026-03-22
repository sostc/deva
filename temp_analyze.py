#!/usr/bin/env python3
from deva.naja.cognition.engine import get_cognition_engine
from collections import Counter
import re

engine = get_cognition_engine()
recent = list(engine.short_memory)[-500:]

print("=== 检查原始内容样本 ===\n")
for i, event in enumerate(recent[-10:]):
    content = getattr(event, 'content', '') or ''
    print(f"--- 样本 {i+1} ---")
    print(content[:200])
    print()

print("\n=== 寻找 AI 相关内容的完整句子 ===\n")
ai_keywords = {'AI', '人工智能', '大模型', 'GPT', 'ChatGPT', 'AIGC', '算力'}

for event in recent:
    content = getattr(event, 'content', '') or ''
    if any(kw in content for kw in ai_keywords):
        print(content[:300])
        print("---")
        break