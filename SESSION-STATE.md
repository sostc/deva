# SESSION-STATE.md - Active Working Memory

**Last Updated:** 2026-03-10T23:55:00Z
**Current Task:** 龙虾思想雷达 v1 - 已实现核心功能

---

## 项目状态

**系统名称**: 龙虾思想雷达 v1 (Lobster Mind Radar)
**状态**: ✅ MVP版本已完成
**位置**: `/Users/spark/pycharmproject/deva/deva/naja/strategy/plugins/lobster_radar.py`

---

## 已实现功能

### 1. 核心策略 (`lobster_radar.py`)
- ✅ 统一事件结构 (LobsterEvent)
- ✅ 注意力评分系统 (5维度评分)
- ✅ 主题聚类 (在线聚类 + 最近邻)
- ✅ 漂移检测 (River ADWIN)
- ✅ 短期记忆 (1000事件)
- ✅ 主题库管理 (最多50个主题)
- ✅ 信号生成 (6种信号类型)
- ✅ 思想报告生成

### 2. Web UI (`home/lobster_tab.py`)
- ✅ 独立Tab页面
- ✅ 实时状态面板
- ✅ 主题云图
- ✅ 注意力时间线
- ✅ 信号流显示
- ✅ 思想报告展示
- ✅ 控制按钮 (刷新/报告/清空/测试)

### 3. Naja集成
- ✅ 策略插件化 (符合naja策略接口)
- ✅ Web路由配置 (`/lobster`)
- ✅ 导航菜单集成
- ✅ 模块初始化文件

---

## 系统架构

```
数据源 (tick/news/text)
    ↓
LobsterEvent (统一事件)
    ↓
注意力评分 (5维度)
    ↓
主题聚类 (River/最近邻)
    ↓
信号生成 → naja信号流
    ↓
Web UI展示
```

---

## 信号类型

1. **TOPIC_EMERGE** - 新主题出现 🟢
2. **TOPIC_GROW** - 主题快速增长 🔵
3. **TOPIC_FADE** - 主题消退 ⚪
4. **HIGH_ATTENTION** - 高注意力事件 🔴
5. **TREND_SHIFT** - 趋势转变 🟣
6. **DRIFT_DETECTED** - 检测到漂移 🟡

---

## 待完善功能

- [ ] 集成真实数据源 (tick/新闻)
- [ ] 接入naja信号流系统
- [ ] 添加周期性自我总结任务
- [ ] 使用sentence-transformers替代简化embedding
- [ ] 中期/长期记忆持久化
- [ ] 思想对话模块 (大模型集成)

---

## 使用方式

1. 启动naja: `python -m deva.naja`
2. 访问: `http://localhost:8080/lobster`
3. 绑定数据源到策略
4. 查看实时思想雷达

---

## 核心代码

```python
# 策略使用示例
from deva.naja.strategy.plugins import LobsterRadarStrategy

radar = LobsterRadarStrategy(config={
    "short_term_size": 1000,
    "topic_threshold": 0.7,
    "attention_threshold": 0.7,
})

# 处理记录
signals = radar.process_record(record)

# 获取报告
report = radar.get_memory_report()
thought_report = radar.generate_thought_report()
```
