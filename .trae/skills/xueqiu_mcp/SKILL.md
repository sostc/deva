---
name: "xueqiu_mcp"
description: "雪球 MCP 服务管理器，用于在 Trae IDE 中查询股票数据、指数收益和基金信息。"
---

# 雪球 MCP 服务

This skill provides a complete suite for managing the Xueqiu MCP service, including installation and configuration.

**Keywords**: 雪球, Xueqiu, MCP, 股票数据, 指数收益, 基金信息

## 功能

1.  **安装**: 克隆仓库并安装依赖。
2.  **配置**: 配置雪球 Token。
3.  **管理服务**: 启动、停止和检查服务状态。
4.  **使用**: 在 AI 助手中查询股票数据、指数收益、深港通/沪港通北向数据、基金相关数据和搜索股票代码。

---

## 安装雪球 MCP

### 步骤 1: 克隆仓库

```bash
git clone https://github.com/liqiongyu/xueqiu_mcp.git
cd xueqiu_mcp
```

### 步骤 2: 安装依赖

```bash
python3 -m venv venv && source venv/bin/activate && pip install -e .
```

### 步骤 3: 配置雪球 Token

1. 在项目根目录创建 `.env` 文件
2. 添加以下内容:
   ```
   XUEQIU_TOKEN="xq_a_token=xxxxx;u=xxxx"
   ```

### 步骤 4: 启动服务

```bash
source venv/bin/activate && python main.py
```

---

## 管理雪球 MCP 服务

### 启动服务

```bash
cd xueqiu_mcp && source venv/bin/activate && python main.py
```

### 停止服务

在运行服务的终端中按 `Ctrl+C` 停止。

### 检查服务状态

服务启动后会显示 FastMCP 启动信息，表示服务运行正常。

---

## 使用方法

在 Trae IDE 中，您可以通过雪球 MCP 服务查询以下信息：

- **股票实时行情**
- **指数收益**
- **深港通/沪港通北向数据**
- **基金相关数据**
- **关键词搜索股票代码**

服务运行后，AI 助手会自动检测并使用雪球 MCP 服务。