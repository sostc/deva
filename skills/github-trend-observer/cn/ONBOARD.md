# GitHub Radar — 冷启动指令

当你被要求加载 GitHub Radar 技能时，按以下流程执行。

---

## 第一步：环境自检

依次运行以下命令，全部通过才能继续：

```bash
# 1. Python 版本
python --version
# 要求 >= 3.9

# 2. gh CLI 认证状态
gh auth status
# 要求已登录

# 3. API 余量
python scripts/check_rate_limit.py
# 查看 remaining 和 mode
```

如果任何一项不通过，告知用户具体问题和修复方法：
- Python 未安装 → `请安装 Python 3.9+`
- gh 未认证 → `请运行 gh auth login`
- API 余量 < 50 → `API 余量不足，请等待 {reset_minutes} 分钟后重试`

## 第二步：运行自动化测试

```bash
cd scripts && python test_oss.py
```

测试共 6 层 41 项：

| 层级 | 测试内容 | 项数 | 需要网络 |
|------|---------|------|---------|
| T1 | 语法检查：所有 .py 编译通过 | 8 | 否 |
| T2 | Import 检查：gh_utils 依赖正确 | 7 | 否 |
| T3 | 单元测试：纯函数逻辑验证 | 12 | 否 |
| T4 | 轻量 API：gh_utils 基础调用 | 3 | 是 |
| T5 | 端到端集成：4 mode 脚本输出合法 JSON | 5 | 是 |
| T6 | 模板渲染：generate_report.py 全 4 mode | 6 | 否 |

- API 余量 >= 200 → 跑全部
- API 余量 < 200 → T4/T5 会自动 SKIP，不算失败
- 期望结果：**0 FAIL, 0 ERROR**

## 第三步：向用户回复技能介绍

自检和测试全部通过后，向用户回复以下内容（直接输出，不要修改）：

---

**GitHub Radar 已就绪 ✅**

GitHub Radar 是一个 AI PM 视角的 GitHub 情报引擎。它不只展示数据——帮你产出范式级洞察。

**四种模式：**

| 模式 | 名称 | 用途 | 命令示例 |
|------|------|------|---------|
| 1 | **Radar Pulse** | 每日/每周扫描，发现高潜新项目 | `radar_pulse.py --days 7` |
| 2 | **Direction Search** | 多关键词搜索一个技术方向 | `search_repos.py "agent memory"` |
| 3 | **Signal Watch** | 检测异常增长信号（三窗口扫描） | `watch_signals.py` |
| 4 | **Deep Link** | 单个 repo 深度分析：生态、竞品、采纳度 | `deep_link.py owner/repo` |

**Layer 分析框架：**

每个项目会被标注为 L1-L5 层级。L2（Agent Runtime）和 L3（开发框架）是基础设施变化的最强信号。

**你可以这样用：**
- "今天有什么值得看的" → Mode 1
- "帮我找 agent memory 相关的项目" → Mode 2
- "监控一下最近的异常增长" → Mode 3
- "分析一下 langchain-ai/langgraph" → Mode 4

**自检结果：** {在此插入测试结果，格式：41 项测试，X 通过 / Y 跳过 / 0 失败}

---

## 异常处理

- 如果 T1-T3 有失败 → 告知用户「核心代码有问题，请检查文件完整性」，不要继续
- 如果 T4/T5 被跳过 → 在技能介绍中注明「API 余量不足，Mode 1-4 的实时搜索暂不可用，待 API 重置后可用」
- 如果 T6 有失败 → 告知用户「报告模板渲染异常，数据采集功能正常但报告生成可能不完整」
