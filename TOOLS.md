# TOOLS.md - Tool Configuration & Notes

> Document tool-specific configurations, gotchas, and credentials here.

---

## Credentials Location

All credentials stored in `.credentials/` (gitignored).

---

## Naja CLI (`bin/naja`)

**Status:** ✅ Working

**Configuration:**
- 后台服务管理: `naja -s start/stop/reload/restart/status`
- PID 文件: `~/.naja/naja.pid`
- 端口文件: `~/.naja/naja.port`
- 前台模式: `python -m deva.naja`

**Gotchas:**
- 热重启使用 SIGUSR1 信号
- 端口占用时会自动检测并提示

---

## macOS 托盘 (`scripts/start_tray.py`)

**Status:** ✅ Working

**Configuration:**
- 每 30 秒自动刷新数据
- 通过端口文件与 Naja 进程通信

**Gotchas:**
- 使用 subprocess.Popen 而非 os.fork()（macOS 兼容性）

---

## 通知适配器

**Status:** ✅ Working (DingTalk)

**Configuration:**
- DingTalk: 已配置
- iMessage: 已配置（+8618626880688）

---

## Skills 体系

**Status:** ✅ Working

**Configuration:**
- 技能目录: `skills/`
- 每个技能包含 `SKILL.md` 定义
- 通过 NajaAgent 对话门面调用

---

*Add whatever helps you do your job. This is your cheat sheet.*
