# Agent 安装指南

本指南介绍如何通过一句话让别人在 agent 中安装 naja-api 技能。

## 安装方法

### 方法 1：使用 GitHub 地址直接安装

只需发送以下命令给对方，对方在 agent 中执行即可完成安装：

```
install skill https://github.com/sostc/naja-api-skill
```

### 方法 2：使用简短链接（可选）

如果 GitHub 地址过长，可以使用短链接服务生成一个简短的链接，例如：

```
install skill https://bit.ly/naja-api-skill
```

## 安装过程

当对方执行安装命令后，agent 会自动：

1. **检测 deva**：检查 `import deva` 和 `deva.naja` 模块是否可用
2. **安装 deva**（如未安装）：
   - 安装 Python 依赖（aiohttp、requests、pyyaml）
   - 克隆 deva 仓库（`https://github.com/sostc/deva.git`）
   - 执行 `pip install -e .` 安装 deva
   - 安装 river 库（在线学习）
3. **验证安装**：确认 `import deva` 和 `deva.naja` 模块加载成功
4. **启动 naja**（如未运行）：
   - 检测端口 8080 是否已有 naja 运行
   - 如未运行，自动执行 `python -m deva.naja --port 8080`（后台运行）
   - 等待最多 15 秒验证启动成功
5. **最终验证**：调用 `/api/system/status` 确认系统健康

### 为什么安装后要启动 naja？

naja-api 技能是一个**客户端**，它通过 HTTP API 与 naja 系统通信。naja 系统是**服务端**，必须先启动才能提供数据。

启动 naja 后，以下能力才会生效：
- 认知系统（叙事、记忆、注意力）
- 注意力系统（Manas 末那识、和谐度、决策）
- 知识库（因果知识、学习状态）
- 市场热点（A股、美股双市场）
- Bandit 决策系统
- 雷达新闻系统

## 安装后操作

安装完成后，naja 系统应该已经在后台运行。用户可以：

### 1. 验证系统状态

```bash
curl -s http://localhost:8080/api/system/status | python3 -m json.tool
```

### 2. 使用技能

```bash
# 查看认知叙事
curl -s http://localhost:8080/api/cognition/memory | python3 -m json.tool

# 查看 Manas 末那识
curl -s http://localhost:8080/api/attention/manas/state | python3 -m json.tool

# 查看知识库
curl -s http://localhost:8080/api/knowledge/list | python3 -m json.tool
```

### 3. 停止 naja（如需要）

```bash
lsof -ti:8080 | xargs kill
```

### 4. 重新启动 naja

```bash
cd deva && python -m deva.naja --port 8080 &
```

## 故障排除

### 安装失败

- **网络问题**：检查能否访问 `github.com`
- **Python 版本**：需要 Python 3.7+
- **权限问题**：脚本使用 `--break-system-packages` 标志

### naja 启动超时

- naja 首次启动需要初始化知识库和数据库，可能需要 20-30 秒
- 查看日志：`tail -f /tmp/naja.log`
- 手动启动：`cd deva && python -m deva.naja --port 8080`

### 端口被占用

- 检查：`lsof -i:8080`
- 换端口：`python -m deva.naja --port 8081`

## 示例对话

**你**：请安装 naja-api 技能

**对方**：已执行安装脚本...

**对方**：
```
[1/5] 检查 Python 版本... ✅
[2/5] 检测 deva 是否已安装... ❌ 未安装，开始安装...
[3/5] 验证安装... ✅
[4/5] 检测 naja 运行状态... ❌ 未运行，正在启动...
  ✅ naja 启动成功！（耗时 12 秒）
[5/5] 最终验证... ✅ 系统状态: 🟢 正常 (10/10)
```

**你**：安装完成！naja 系统已自动启动，现在可以使用所有 API 了。

## 注意事项

- 安装脚本会自动检测 deva 是否已安装，避免重复安装
- naja 启动后会在后台持续运行，提供实时数据服务
- 非交易时段，市场热点和持仓数据为空是正常现象
- 系统日志位于 `/tmp/naja.log`
