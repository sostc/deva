# Naja API 技能发布指南

本指南详细介绍如何发布 naja-api 技能，让其他人能够轻松安装并使用它。

## 技能结构

技能目录结构如下：

```
skills/naja-api/
├── _meta.json          # 技能元数据
├── SKILL.md            # 技能描述
├── README.md           # 详细文档
├── PUBLISHING.md       # 本发布指南
└── scripts/
    ├── api_client.py   # API 客户端脚本
    ├── install_naja.sh # 自动安装脚本
    ├── monitor_system.sh # 系统监控脚本
    ├── monitor_market.sh # 市场监控脚本
    └── export_cognition.sh # 认知数据导出脚本
```

## 发布步骤

### 1. 准备技能包

1. 确保所有文件都已正确配置
2. 检查 `_meta.json` 中的版本号和依赖信息
3. 确保安装脚本 `install_naja.sh` 具有执行权限

### 2. 发布到技能仓库

#### 方法 1：发布到 GitHub

1. 在 GitHub 上创建一个新的仓库，例如 `naja-api-skill`
2. 将技能目录的内容推送到该仓库
3. 在仓库的 README 中添加安装和使用说明

#### 方法 2：发布到技能市场

如果有技能市场平台，按照平台的发布流程进行操作。

## 安装说明

### 自动安装流程

当用户安装此技能时，系统会自动执行以下步骤：

1. **克隆技能仓库**：用户将技能仓库克隆到本地
2. **运行安装脚本**：执行 `install_naja.sh` 脚本
3. **安装依赖**：脚本会自动安装所有必要的依赖
4. **配置环境**：设置必要的环境变量

### 手动安装步骤

如果自动安装失败，用户可以按照以下步骤手动安装：

1. **克隆技能仓库**
   ```bash
   git clone https://github.com/yourusername/naja-api-skill.git
   cd naja-api-skill
   ```

2. **运行安装脚本**
   ```bash
   bash scripts/install_naja.sh
   ```

3. **检查安装状态**
   ```bash
   python -m deva.naja --version
   ```

## 使用前的准备

在使用技能之前，必须确保 naja 系统已经启动：

1. **启动 naja 系统**
   ```bash
   python -m deva.naja --port 8080
   ```

2. **验证系统状态**
   ```bash
   curl http://localhost:8080/api/health
   ```

## 技能使用示例

### 基本命令

```bash
# 系统状态检查
python scripts/api_client.py system-status

# 市场热点分析
python scripts/api_client.py market-hotspot

# 认知系统状态
python scripts/api_client.py cognition-status
```

### 监控脚本

```bash
# 监控系统状态
bash scripts/monitor_system.sh

# 监控市场热点
bash scripts/monitor_market.sh

# 导出认知系统数据
bash scripts/export_cognition.sh
```

## 故障排除

### 常见问题

1. **naja 启动失败**
   - 检查端口是否被占用
   - 检查依赖是否正确安装

2. **API 调用失败**
   - 确认 naja 系统正在运行
   - 检查网络连接
   - 验证 API 端点是否正确

3. **安装脚本执行失败**
   - 检查 Python 版本（需要 Python 3.7+）
   - 确保有足够的权限
   - 检查网络连接

### 日志查看

naja 系统的日志可以在启动目录中查看，或者通过 API 端点获取：

```bash
curl http://localhost:8080/api/system/logs
```

## 版本管理

- 技能版本在 `_meta.json` 文件中定义
- 每次更新技能时，应递增版本号
- 发布新版本时，应更新 `README.md` 中的使用说明

## 贡献指南

欢迎对技能进行改进和扩展：

1. Fork 技能仓库
2. 进行修改
3. 提交 Pull Request
4. 等待审核和合并

## 联系方式

如果有任何问题或建议，请通过以下方式联系：

- GitHub Issues：在技能仓库中创建 issue
- 电子邮件：contact@deva-ai.com

---

**注意**：使用此技能前，请确保您已经了解 naja 系统的基本概念和操作方法。