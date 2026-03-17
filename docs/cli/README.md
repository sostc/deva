# CLI 命令行工具指南

> 基于最新代码结构（2026-03-17）

## 概述

Deva CLI 提供命令行工具用于技能管理和系统运维。

## 目录结构

```
cli/
├── skills_store_cli.py    # 技能商店 CLI
├── skills_upgrade.py      # 技能升级
├── metadata.json          # 元数据
├── version.json           # 版本信息
├── install.sh             # 安装脚本
└── plugin/                # 插件目录
```

## 主要命令

### 技能商店

```bash
# 列出可用技能
python cli/skills_store_cli.py list

# 安装技能
python cli/skills_store_cli.py install <skill-name>

# 卸载技能
python cli/skills_store_cli.py uninstall <skill-name>

# 搜索技能
python cli/skills_store_cli.py search <keyword>
```

### 技能升级

```bash
# 升级所有技能
python cli/skills_upgrade.py

# 升级指定技能
python cli/skills_upgrade.py <skill-name>
```

## Bin 目录

```
bin/
├── oc-skills    # OpenClaw 技能命令
└── skillhub     # SkillHub 命令
```

## 使用方式

```bash
# 添加执行权限
chmod +x bin/oc-skills
chmod +x bin/skillhub

# 使用技能命令
./bin/oc-skills list
./bin/skillhub search <keyword>
```

## 相关文档

- [skills_store.md](skills_store.md)
- [skillhub_install.md](../skillhub_install.md)
