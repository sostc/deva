# Naja API 技能快速开始指南

本指南将帮助您快速安装和使用 naja-api 技能。

## 快速安装

### 步骤 1：克隆技能仓库

```bash
git clone https://github.com/yourusername/naja-api-skill.git
cd naja-api-skill
```

### 步骤 2：运行安装脚本

```bash
bash scripts/install_naja.sh
```

该脚本会自动：
- 检查 Python 版本
- 创建虚拟环境
- 安装必要的依赖
- 克隆并安装 deva naja
- 安装 river 库（处理版本兼容性）

### 步骤 3：启动 naja 系统

在使用技能之前，必须启动 naja 系统：

```bash
python -m deva.naja --port 8080
```

### 步骤 4：验证系统状态

```bash
curl http://localhost:8080/api/health
```

如果返回 `{"status": "healthy"}`，则表示 naja 系统已成功启动。

## 基本使用

### 系统状态检查

```bash
python scripts/api_client.py system-status
```

### 市场热点分析

```bash
python scripts/api_client.py market-hotspot
```

### 认知系统状态

```bash
python scripts/api_client.py cognition-status
```

## 监控脚本

### 监控系统状态

```bash
bash scripts/monitor_system.sh
```

### 监控市场热点

```bash
bash scripts/monitor_market.sh
```

### 导出认知系统数据

```bash
bash scripts/export_cognition.sh
```

## 常见问题

### Q: naja 启动失败怎么办？
A: 检查端口是否被占用，尝试使用不同的端口，例如 `--port 8081`

### Q: API 调用失败怎么办？
A: 确认 naja 系统正在运行，检查网络连接和 API 端点是否正确

### Q: 安装脚本执行失败怎么办？
A: 检查 Python 版本（需要 Python 3.7+），确保有足够的权限，检查网络连接

## 详细文档

- [README.md](README.md) - 详细的技能文档
- [PUBLISHING.md](PUBLISHING.md) - 技能发布指南
- [SKILL.md](SKILL.md) - 技能描述

---

**提示**：如果您是第一次使用 naja 系统，建议先阅读 [README.md](README.md) 了解更多详细信息。