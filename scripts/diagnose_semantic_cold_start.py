#!/usr/bin/env python
"""诊断脚本：验证 SemanticColdStart 完整性"""
import os
import sys
import time

os.environ['NAJA_LAB_MODE'] = '1'

print("=" * 70)
print("诊断：语义冷启动系统")
print("=" * 70)

from deva.naja.cognition.semantic.semantic_cold_start import SemanticColdStart, DEFAULT_PROMPT_TEMPLATE

print("\n[1] 创建 SemanticColdStart 实例...")
config = {
    "semantic_cold_start_enabled": True,
    "semantic_seed_terms": ["AI", "算力", "芯片"],
    "semantic_default_lambda": 0.005,
    "semantic_industry_lambdas": {"电力": 0.002, "AI": 0.01},
}
cold_start = SemanticColdStart(config)
print(f"    enabled: {cold_start.enabled}")
print(f"    seeds: {cold_start.seeds}")
print(f"    default_lambda: {cold_start.default_lambda}")
print(f"    graph: {cold_start.graph}")

print("\n[2] 构建 prompt...")
prompt = cold_start.build_prompt()
print(f"    prompt 长度: {len(prompt)}")
print(f"    prompt 预览:\n{cold_start.build_prompt(['量子计算'])[:200]}...")

print("\n[3] 模拟 LLM 返回...")
llm_response = {
    "seeds": ["AI", "算力", "芯片"],
    "nodes": [
        {"term": "GPU", "level": 1, "relation": "supply_chain", "confidence": 0.78},
        {"term": "CPO", "level": 1, "relation": "tech_stack", "confidence": 0.72},
        {"term": "液冷", "level": 2, "relation": "infrastructure", "confidence": 0.62},
        {"term": "HBM", "level": 2, "relation": "memory", "confidence": 0.65},
    ],
    "edges": [
        {"from": "算力", "to": "GPU", "type": "enables"},
        {"from": "CPO", "to": "液冷", "type": "depends_on"},
        {"from": "芯片", "to": "HBM", "type": "requires"},
    ],
    "industry_decay": [
        {"term": "电力", "lambda": 0.002},
        {"term": "AI", "lambda": 0.01},
    ],
    "created_at": time.time(),
}

print("\n[4] 应用 LLM 返回...")
graph = cold_start.apply_graph_payload(llm_response)
print(f"    graph nodes count: {len(graph.get('nodes', []))}")
print(f"    graph edges count: {len(graph.get('edges', []))}")

print("\n[5] 获取摘要...")
summary = cold_start.get_summary(limit=10)
print(f"    seeds: {summary.get('seeds')}")
print(f"    top_nodes:")
for node in summary.get('top_nodes', []):
    print(f"      - {node.get('term')}: weight={node.get('weight')}, level={node.get('level')}")

print("\n[6] 测试 CognitionEngine 集成...")
from deva.naja.cognition import get_cognition_engine
cog_engine = get_cognition_engine()
news_mind = cog_engine._news_mind
print(f"    CognitionEngine._news_mind.semantic_graph: {news_mind.semantic_graph is not None}")
print(f"    CognitionEngine._news_mind.semantic_graph 节点数: {len(news_mind.semantic_graph.get('nodes', []))}")

print("\n[7] 测试 prompt 构建和更新...")
prompt = news_mind.build_semantic_cold_start_prompt(["半导体", "光刻机"])
print(f"    构建 prompt 成功: {len(prompt) > 0}")

print("\n" + "=" * 70)
print("诊断完成")
print("=" * 70)