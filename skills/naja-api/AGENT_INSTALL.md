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

1. **克隆技能仓库**：从 GitHub 克隆技能代码
2. **安装依赖**：运行 `install_naja.sh` 脚本安装 deva naja 及其依赖
3. **配置技能**：根据 `_meta.json` 配置技能参数
4. **验证安装**：检查技能是否正确安装

## 安装后操作

安装完成后，用户需要：

1. **启动 naja 系统**：
   ```bash
   python -m deva.naja --port 8080
   ```

2. **验证系统状态**：
   ```bash
   curl http://localhost:8080/api/health
   ```

3. **使用技能**：通过 agent 命令或直接运行脚本使用技能功能

## 故障排除

### 安装失败

如果安装失败，可能的原因：
- 网络连接问题
- GitHub 仓库地址错误
- 权限不足

### 启动失败

如果 naja 系统启动失败，可能的原因：
- 端口被占用
- 依赖未正确安装
- 环境配置问题

## 示例对话

**你**：请安装 naja-api 技能，使用这个命令：install skill https://github.com/sostc/naja-api-skill

**对方**：已执行命令，正在安装...

**对方**：安装成功！

**你**：现在请启动 naja 系统：python -m deva.naja --port 8080

**对方**：已启动 naja 系统

**你**：请验证系统状态：curl http://localhost:8080/api/health

**对方**：返回 {"status": "healthy"}

**你**：现在可以使用 naja-api 技能了！

## 注意事项

- 确保对方的环境已安装 Python 3.7+
- 确保对方有足够的权限执行安装操作
- 安装过程可能需要几分钟时间，取决于网络速度
- 安装完成后，必须启动 naja 系统才能使用技能

---

**提示**：如果对方在安装过程中遇到问题，请参考 [PUBLISHING.md](PUBLISHING.md) 和 [QUICKSTART.md](QUICKSTART.md) 中的故障排除部分。