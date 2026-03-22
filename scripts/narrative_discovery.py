#!/usr/bin/env python3
"""
叙事关键词自动挖掘脚本 v2
从新闻数据中自动发现新关键词，并更新到叙事追踪器
"""
from deva.naja.cognition.engine import get_cognition_engine
from collections import Counter
import re

STOPWORDS = set([
    '的', '了', '是', '在', '和', '与', '或', '以及', '等', '对', '为', '有', '可', '被', '将', '该', '这', '那',
    '之', '以', '而', '但', '若', '则', '因', '所', '于', '上', '下', '中', '内', '外', '前', '后', '年', '月',
    '日', '时', '分', '秒', '万', '亿', '元', '美元', '人民币', '美国', '中国', '全球', '市场', '公司', '数据',
    '消息', '报道', '金十', '讯', '金十数据', '表示', '称', '据', '通过', '由于', '因此', '但是', '然而',
    '同时', '此外', '另外', '包括', '其中', '以及', '有关', '关于', '相关', '进行', '开始', '已经', '正在',
    '可能', '将会', '可以', '能够', '应该', '必须', '需要', '要求', '希望', '认为', '觉得', '知道', '看到',
    '出现', '发生', '产生', '带来', '造成', '导致', '引起', '实现', '完成', '结束', '继续', '保持', '增加',
    '减少', '下降', '上升', '增长', '提高', '降低', '改善', '加剧', '缓解', '解决', '处理', '管理', '控制',
    '影响', '作用', '效果', '结果', '目的', '意义', '价值', '价格', '成交', '成交量', '万手', '亿元',
    '一定', '一些', '一些', '这种', '这种', '各种', '其他', '其余', '每个', '各个', '整个', '全部', '部分',
    '主要', '重要', '重大', '一个', '一些', '这种', '怎样', '如何', '为什么', '因为', '所以', '如果', '即使',
    '不仅', '而且', '或者', '还是', '以及', '及其', '之于', '对于', '关于', '由于', '基于', '根据', '按照',
    '通过', '经过', '随着', '沿着', '朝着', '为了', '以便', '只要', '只有', '除非', '即使', '即便', '虽然',
    '尽管', '不过', '然而', '但是', '而后', '于是', '因此', '故', '故而', '是以', '故此', '以致', '乃至',
])

CHINESE_WORD = re.compile(r'[\u4e00-\u9fff]{2,6}')
ENGLISH_WORD = re.compile(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+|[A-Z]{2,}(?:[A-Z]{2,})*|[A-Za-z]{4,}')
DIGIT_PAT = re.compile(r'^\d+$')

def clean_html(text):
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\{[^}]+\}', ' ', text)
    return text

def extract_words(text):
    words = []
    text = clean_html(text)
    for m in CHINESE_WORD.finditer(text):
        w = m.group()
        if w not in STOPWORDS and len(w) >= 2:
            words.append(w)
    for m in ENGLISH_WORD.finditer(text):
        w = m.group()
        if w not in STOPWORDS and len(w) >= 3:
            words.append(w)
    return words

def main():
    engine = get_cognition_engine()
    recent = list(engine.short_memory)[-500:]

    all_text = ""
    for event in recent:
        content = getattr(event, 'content', '') or ''
        all_text += content + " "

    words = extract_words(all_text)
    word_counts = Counter(words)

    print("=" * 70)
    print("叙事关键词自动挖掘报告 v2")
    print("=" * 70)

    print("\n📊 Top 80 高频有意义词汇:\n")
    for i, (word, count) in enumerate(word_counts.most_common(80), 1):
        print(f"  {i:2d}. {word}: {count}")

    from deva.naja.cognition.narrative_tracker import DEFAULT_NARRATIVE_KEYWORDS
    existing_kws = set()
    for kws in DEFAULT_NARRATIVE_KEYWORDS.values():
        existing_kws.update(kws)

    print("\n\n💡 新叙事候选词（高频且未被现有叙事覆盖）:\n")
    candidates = [(w, c) for w, c in word_counts.most_common(200)
                 if w not in existing_kws and not DIGIT_PAT.match(w) and len(w) >= 2]

    print(f"  发现 {len(candidates)} 个候选词:\n")
    for word, count in candidates[:30]:
        print(f"    {word}: {count}")

    print("\n\n🔧 建议添加的关键词（按叙事分类）:\n")

    nar_seeds = {
        'AI': {'AI', '人工智能', '大模型', 'GPT'},
        '芯片': {'芯片', '半导体', 'GPU', 'CPU'},
        '新能源': {'新能源', '光伏', '锂电'},
        '医药': {'医药', '医疗', '疫苗'},
    }

    for nar, seeds in nar_seeds.items():
        nar_text = ""
        for event in recent:
            content = getattr(event, 'content', '') or ''
            if any(s in content for s in seeds):
                nar_text += content + " "

        nar_words = extract_words(nar_text)
        nar_filtered = [w for w in nar_words if w not in existing_kws and not DIGIT_PAT.match(w)]
        top_nar = Counter(nar_filtered).most_common(20)

        print(f"  【{nar}】可添加的关联词:")
        for word, count in top_nar[:8]:
            if count >= 2:
                print(f"    \"{word}\",  # {count}次")
        print()

    print("\n🌟 高置信度新叙事候选（跨多个类别的高频词）:\n")
    all_nar_seeds = set()
    for seeds in nar_seeds.values():
        all_nar_seeds.update(seeds)

    multi_nar_words = Counter()
    for event in recent:
        content = getattr(event, 'content', '') or ''
        matched_seeds = sum(1 for s in all_nar_seeds if s in content)
        if matched_seeds >= 2:
            for w in extract_words(content):
                if w not in existing_kws and w not in all_nar_seeds and not DIGIT_PAT.match(w):
                    multi_nar_words[w] += 1

    print("  同时出现在多个叙事中的词:")
    for word, count in multi_nar_words.most_common(15):
        if count >= 3:
            print(f"    {word}: {count}次")

if __name__ == "__main__":
    main()