# Deva 项目版本管理规范

## 📊 当前版本状况分析

### 问题识别

1. **版本号混乱**
   - setup.py: `1.4.1`
   - deva/__init__.py: `1.4.1`
   - 无 Git Tags 记录
   - 无 CHANGELOG 文件

2. **发布流程缺失**
   - 没有正式的发布流程
   - 没有版本提交规范
   - 没有发布检查清单

3. **历史记录不完整**
   - 旧的 Git Tags 丢失
   - 只有 0.2 版本的提交记录
   - 1.x 版本无追溯记录

---

## 🎯 版本管理方案

### 1. 语义化版本规范 (SemVer)

采用 [Semantic Versioning 2.0.0](https://semver.org/) 规范：

```
主版本号。次版本号。修订版本号
MAJOR.MINOR.PATCH
```

**版本号规则：**

| 变更类型 | 版本号递增 | 示例 |
|---------|-----------|------|
| 不兼容的 API 变更 | MAJOR | 1.0.0 → 2.0.0 |
| 向后兼容的功能新增 | MINOR | 1.4.1 → 1.5.0 |
| 向后兼容的问题修正 | PATCH | 1.4.0 → 1.4.1 |

**预发布版本：**

```
1.5.0-alpha.1    # Alpha 测试版
1.5.0-beta.1     # Beta 测试版
1.5.0-rc.1       # Release Candidate
1.5.0            # 正式版
```

### 2. 版本号同步

**统一版本号位置：**

```python
# deva/__init__.py
__version__ = '1.5.0'

# setup.py
setup(
    name='deva',
    version='1.5.0',
    # ...
)
```

**自动化同步（推荐）：**

```python
# setup.py
import os

# 从 __init__.py 读取版本
def get_version():
    init_py = os.path.join(os.path.dirname(__file__), 'deva', '__init__.py')
    with open(init_py, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip("'")

setup(
    name='deva',
    version=get_version(),
    # ...
)
```

### 3. Git Tag 管理

**创建 Tag 的时机：**

- ✅ 每个正式版发布前
- ✅ 每个预发布版本（alpha/beta/rc）
- ✅ 确保 Tag 与版本号一致

**Tag 命名规范：**

```bash
# 正式版
v1.4.1
v1.5.0
v2.0.0

# 预发布版
v1.5.0-alpha.1
v1.5.0-beta.1
v1.5.0-rc.1
```

**创建 Tag 的命令：**

```bash
# 创建带注解的 Tag（推荐）
git tag -a v1.5.0 -m "Release version 1.5.0"

# 推送到远程
git push origin v1.5.0

# 推送所有 Tag
git push origin --tags
```

### 4. 版本提交规范

**提交消息格式：**

```bash
# 新版本发布
git commit -m "release: 发布版本 1.5.0"

# 或英文
git commit -m "release: Version 1.5.0"
```

**完整的发布提交流程：**

```bash
# 1. 更新版本号
# 编辑 deva/__init__.py 和 setup.py

# 2. 更新 CHANGELOG.md
# 添加新版本的变更日志

# 3. 提交版本更新
git add deva/__init__.py setup.py CHANGELOG.md
git commit -m "release: 发布版本 1.5.0"

# 4. 创建 Git Tag
git tag -a v1.5.0 -m "Release version 1.5.0"

# 5. 推送到远程
git push origin master
git push origin v1.5.0
```

---

## 📝 CHANGELOG 规范

### CHANGELOG.md 结构

```markdown
# 变更日志

本文档记录 Deva 项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增
- 功能描述

### 修复
- Bug 描述

### 变更
- 变更描述

## [1.5.0] - 2026-02-26

### 新增
- 完整的文档体系（快速开始、安装指南、使用手册等）
- Admin UI 文档中心集成
- 文件组织优化（docs/, scripts/, tests/）

### 修复
- 数据源列表页自动刷新
- 任务管理面板 UI 问题

### 变更
- 重构项目文件结构
- 优化文档渲染性能

### 移除
- 根目录临时文件

## [1.4.1] - 2026-02-20

### 修复
- 修复数据源缓存问题
- 修复 UI 显示异常

## [1.4.0] - 2026-02-15

### 新增
- 任务管理功能
- AI 代码生成

### 变更
- 优化 Admin UI
```

### 变更类型说明

| 类型 | 说明 | 示例 |
|------|------|------|
| **新增** (Added) | 新功能 | 新增文档中心 |
| **修复** (Fixed) | Bug 修复 | 修复刷新问题 |
| **变更** (Changed) | 现有功能变更 | 重构文件结构 |
| **移除** (Removed) | 功能删除 | 移除旧 API |
| **弃用** (Deprecated) | 即将删除的功能 | 弃用旧配置方式 |
| **安全** (Security) | 安全修复 | 修复 XSS 漏洞 |

---

## 🚀 发布流程

### 发布检查清单

**发布前检查：**

- [ ] 所有测试通过 (`pytest tests/`)
- [ ] 代码审查完成
- [ ] 文档已更新
- [ ] CHANGELOG.md 已更新
- [ ] 版本号已更新
- [ ] 无未提交的更改

**发布步骤：**

```bash
# 1. 运行测试
pytest tests/

# 2. 构建分发包
python setup.py sdist bdist_wheel

# 3. 本地测试安装
pip install -e .

# 4. 更新版本号和 CHANGELOG
# 编辑 deva/__init__.py
# 编辑 CHANGELOG.md

# 5. 提交
git add deva/__init__.py setup.py CHANGELOG.md
git commit -m "release: 发布版本 X.Y.Z"

# 6. 创建 Tag
git tag -a vX.Y.Z -m "Release version X.Y.Z"

# 7. 推送
git push origin master
git push origin vX.Y.Z

# 8. 发布到 PyPI（可选）
twine upload dist/*
```

**发布后验证：**

- [ ] Git Tag 已创建
- [ ] 远程仓库已更新
- [ ] PyPI 包已发布（如适用）
- [ ] GitHub Release 已创建（可选）

---

## 📋 版本历史恢复建议

### 当前状况

- 最新版本：1.4.1（无 Tag）
- 最旧 Tag：无
- 提交历史：有 0.2 版本提交记录

### 恢复方案

**方案 A：从当前状态开始（推荐）**

```bash
# 1. 为当前版本创建 Tag
git tag -a v1.4.1 -m "Release version 1.4.1"

# 2. 推送到远程
git push origin v1.4.1
```

**方案 B：恢复旧版本 Tag**

```bash
# 查找 0.2 版本的提交
git log --oneline --all --grep="0.2"

# 为 0.2 版本创建 Tag（假设提交是 8657308）
git tag -a v0.2.0 8657308 -m "Release version 0.2.0"

# 为中间的里程碑创建 Tag（如果知道的话）
# git tag -a v1.0.0 <commit-hash> -m "Release version 1.0.0"

# 为当前版本创建 Tag
git tag -a v1.4.1 -m "Release version 1.4.1"

# 推送所有 Tag
git push origin --tags
```

---

## 🔧 自动化工具

### 版本管理脚本

创建 `scripts/version.py`：

```python
#!/usr/bin/env python
# coding: utf-8
"""
Deva 版本管理工具

使用方法：
    python scripts/version.py show      # 显示当前版本
    python scripts/version.py bump major  # 升级主版本号
    python scripts/version.py bump minor  # 升级次版本号
    python scripts/version.py bump patch  # 升级修订号
    python scripts/version.py tag       # 创建 Git Tag
"""

import re
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
INIT_PY = ROOT / 'deva' / '__init__.py'
SETUP_PY = ROOT / 'setup.py'
CHANGELOG = ROOT / 'CHANGELOG.md'


def get_version():
    """获取当前版本号"""
    with open(INIT_PY, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip("'")
    raise RuntimeError('无法获取版本号')


def set_version(version):
    """设置新版本号"""
    # 更新 __init__.py
    with open(INIT_PY, 'r', encoding='utf-8') as f:
        content = f.read()
    content = re.sub(
        r"__version__ = '[\d.]+'",
        f"__version__ = '{version}'",
        content
    )
    with open(INIT_PY, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # 更新 setup.py
    with open(SETUP_PY, 'r', encoding='utf-8') as f:
        content = f.read()
    content = re.sub(
        r"version='[\d.]+'",
        f"version='{version}'",
        content
    )
    with open(SETUP_PY, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f'✅ 版本号已更新：{version}')


def bump_version(level):
    """升级版本号"""
    current = get_version()
    major, minor, patch = map(int, current.split('.'))
    
    if level == 'major':
        major += 1
        minor = 0
        patch = 0
    elif level == 'minor':
        minor += 1
        patch = 0
    elif level == 'patch':
        patch += 1
    else:
        raise ValueError(f'无效的级别：{level}')
    
    new_version = f'{major}.{minor}.{patch}'
    set_version(new_version)
    return new_version


def create_tag(version):
    """创建 Git Tag"""
    tag_name = f'v{version}'
    
    # 创建带注解的 Tag
    subprocess.run(['git', 'tag', '-a', tag_name, '-m', f'Release version {version}'])
    
    # 推送 Tag
    print(f'✅ 已创建 Tag: {tag_name}')
    print('提示：运行以下命令推送到远程')
    print(f'  git push origin {tag_name}')
    print(f'  git push origin --tags')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'show':
        print(f'当前版本：{get_version()}')
    
    elif command == 'bump':
        if len(sys.argv) < 3:
            print('用法：python scripts/version.py bump <major|minor|patch>')
            sys.exit(1)
        level = sys.argv[2]
        new_version = bump_version(level)
        print(f'新版本：{new_version}')
    
    elif command == 'tag':
        version = get_version()
        create_tag(version)
    
    else:
        print(f'未知命令：{command}')
        sys.exit(1)


if __name__ == '__main__':
    main()
```

**使用示例：**

```bash
# 显示当前版本
python scripts/version.py show

# 升级版本号
python scripts/version.py bump patch  # 1.4.1 -> 1.4.2
python scripts/version.py bump minor  # 1.4.2 -> 1.5.0
python scripts/version.py bump major  # 1.5.0 -> 2.0.0

# 创建 Git Tag
python scripts/version.py tag
```

---

## 📊 版本管理最佳实践

### 1. 版本号规则

- ✅ 使用三位数字：MAJOR.MINOR.PATCH
- ✅ 预发布版本使用后缀：-alpha.1, -beta.1, -rc.1
- ✅ 避免四位数字：1.4.1.0 ❌

### 2. 提交规范

```bash
# ✅ 好的提交
release: 发布版本 1.5.0
feat: 新增文档中心
fix: 修复刷新问题
refactor: 重构文件结构

# ❌ 不好的提交
更新
修复 bug
```

### 3. Tag 管理

```bash
# ✅ 创建带注解的 Tag
git tag -a v1.5.0 -m "Release version 1.5.0"

# ❌ 避免轻量 Tag
git tag v1.5.0  # 无注解
```

### 4. 发布频率

| 版本类型 | 建议频率 | 示例 |
|---------|---------|------|
| PATCH | 每周（按需） | 1.4.1, 1.4.2 |
| MINOR | 每月 | 1.4.0, 1.5.0 |
| MAJOR | 每季度/每年 | 1.0.0, 2.0.0 |

---

## 🔗 相关资源

- [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)
- [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)
- [Git Tag 管理](https://git-scm.com/book/zh/v2/Git-%E5%9F%BA%E7%A1%80-%E6%89%93%E6%A0%87%E7%AD%BE)
- [Python 打包指南](https://packaging.python.org/)

---

**创建时间：** 2026-02-26  
**适用版本：** Deva v1.4.1+  
**维护者：** Deva 团队
