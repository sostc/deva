# Prompts 索引

## 文件说明

本目录包含用于创建数据源和策略的 Prompts 模板。

### 文件列表

| 文件 | 说明 |
|------|------|
| [datasource_prompts.md](datasource_prompts.md) | 数据源创建 Prompts |
| [strategy_prompts.md](strategy_prompts.md) | 策略创建 Prompts |
| [quick_reference.md](quick_reference.md) | 快速参考和模板 |

---

## 快速使用

### 场景1: 创建数据源

使用 `datasource_prompts.md` 中的模板，指定：
- 数据源类型 (tick/kline/news)
- 需要的字段

### 场景2: 创建策略

使用 `strategy_prompts.md` 中的模板，指定：
- 数据源类型
- 输出目标 (radar/memory/bandit/llm)
- 需要的字段

### 场景3: 联合创建

使用 `datasource_prompts.md` 中的 "联合创建" 模板，同时指定数据源和策略。

---

## 推荐流程

1. **确定数据源类型** → tick/kline/news
2. **确定输出目标** → radar/memory/bandit/llm
3. **选择对应模板** → 从 quick_reference.md 复制
4. **填写具体参数** → 代码和数据
5. **检查清单** → quick_reference.md 中的检查项
