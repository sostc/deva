#!/usr/bin/env python
# coding: utf-8
"""
生成 Admin UI 完整文档

基于 Admin UI 的代码结构和功能分析，生成完整的文档体系。
"""

import os
import inspect
import ast
from pathlib import Path
from typing import Dict, List, Any


class AdminUIDocGenerator:
    """Admin UI 文档生成器"""
    
    def __init__(self, admin_ui_dir: str):
        self.admin_ui_dir = Path(admin_ui_dir)
        self.strategy_dir = self.admin_ui_dir / 'strategy'
        self.docs = {}
    
    def analyze_module(self, file_path: Path) -> Dict[str, Any]:
        """分析单个模块文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        try:
            tree = ast.parse(content)
        except:
            return {'error': '解析失败'}
        
        module_info = {
            'name': file_path.stem,
            'path': str(file_path),
            'docstring': ast.get_docstring(tree) or '',
            'classes': [],
            'functions': [],
            'imports': []
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = {
                    'name': node.name,
                    'docstring': ast.get_docstring(node) or '',
                    'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                }
                module_info['classes'].append(class_info)
            
            elif isinstance(node, ast.FunctionDef):
                if not node.name.startswith('_'):
                    func_info = {
                        'name': node.name,
                        'docstring': ast.get_docstring(node) or '',
                        'args': [arg.arg for arg in node.args.args if arg.arg != 'self']
                    }
                    module_info['functions'].append(func_info)
            
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_info['imports'].append(node.module)
        
        return module_info
    
    def generate_module_doc(self, module_info: Dict) -> str:
        """生成单个模块的文档"""
        doc = f"## {module_info['name'].replace('_', ' ').title()}\n\n"
        
        if module_info.get('docstring'):
            doc += f"**说明**: {module_info['docstring']}\n\n"
        
        if module_info['classes']:
            doc += "### 核心类\n\n"
            for cls in module_info['classes']:
                doc += f"#### {cls['name']}\n"
                if cls['docstring']:
                    doc += f"{cls['docstring']}\n"
                doc += f"**方法**: {', '.join(cls['methods'])}\n\n"
        
        if module_info['functions']:
            doc += "### 核心函数\n\n"
            for func in module_info['functions']:
                doc += f"#### {func['name']}\n"
                if func['docstring']:
                    doc += f"{func['docstring']}\n"
                if func['args']:
                    doc += f"**参数**: {', '.join(func['args'])}\n\n"
        
        return doc
    
    def generate_complete_doc(self) -> str:
        """生成完整文档"""
        doc = """# Deva Admin UI 完整文档

## 📖 概述

Deva Admin UI 是一个基于 PyWebIO 和 Tornado 的 Web 管理界面，提供对 Deva 流处理框架的全面管理和监控功能。

### 核心特性

- 🎨 **现代化 UI** - 基于 PyWebIO 的响应式界面
- 🤖 **AI 集成** - AI 代码生成、智能对话
- 📊 **实时监控** - 数据流、任务状态实时监控
- 💾 **持久化** - 策略、数据源、任务的持久化管理
- 🔐 **安全认证** - 用户认证和权限管理
- 🔧 **可扩展** - 模块化设计，易于扩展

---

## 🗂️ 功能模块

"""
        
        # 分析主目录模块
        doc += "### 主界面模块\n\n"
        for py_file in sorted(self.admin_ui_dir.glob('*.py')):
            if py_file.name.startswith('_'):
                continue
            module_info = self.analyze_module(py_file)
            if not module_info.get('error'):
                doc += self.generate_module_doc(module_info)
        
        # 分析 Strategy 模块
        doc += "\n---\n\n### 策略管理模块\n\n"
        for py_file in sorted(self.strategy_dir.glob('*.py')):
            if py_file.name.startswith('_'):
                continue
            module_info = self.analyze_module(py_file)
            if not module_info.get('error'):
                doc += self.generate_module_doc(module_info)
        
        return doc
    
    def generate_quick_start(self) -> str:
        """生成快速开始指南"""
        return """# Deva Admin UI 快速开始

## 🚀 启动 Admin

```bash
# 方法 1：模块方式
python -m deva.admin

# 方法 2：直接运行
python deva/admin.py
```

## 🌐 访问界面

浏览器访问：`http://127.0.0.1:9999`

## 📋 导航菜单

| 菜单 | 路径 | 功能 |
|------|------|------|
| 🏠 首页 | `/` | 系统概览 |
| ⭐ 关注 | `/followadmin` | 关注的内容 |
| 🌐 浏览器 | `/browseradmin` | 浏览器管理 |
| 💾 数据库 | `/dbadmin` | 数据库管理 |
| 🚌 Bus | `/busadmin` | 消息总线 |
| 📊 命名流 | `/streamadmin` | 流管理 |
| 📡 数据源 | `/datasourceadmin` | 数据源管理 |
| 📈 策略 | `/strategyadmin` | 策略管理 |
| 👁 监控 | `/monitor` | 系统监控 |
| ⏰ 任务 | `/taskadmin` | 任务管理 |
| ⚙️ 配置 | `/configadmin` | 系统配置 |
| 📄 文档 | `/document` | 文档中心 |
| 🤖 AI | `/aicenter` | AI 功能中心 |

## 🔐 首次使用

1. 首次访问会提示创建管理员账户
2. 输入用户名和密码（至少 6 位）
3. 登录后即可使用所有功能

## 💡 常用功能

### 1. 查看数据流

- 访问 **📊 命名流**
- 查看所有命名流的状态
- 点击流名称查看详情

### 2. 管理策略

- 访问 **📈 策略**
- 创建新策略（支持 AI 生成）
- 查看策略执行状态
- 编辑策略代码

### 3. 配置数据源

- 访问 **📡 数据源**
- 创建数据源（支持 AI 生成）
- 配置数据源参数
- 查看数据源状态

### 4. 使用 AI 功能

- 访问 **🤖 AI**
- 配置 AI 模型（Kimi/DeepSeek 等）
- 使用代码生成功能
- 体验智能对话

---

## 📚 详细文档

- [Admin UI 架构](admin_ui_architecture.md) - 架构说明
- [策略管理](strategy_guide.md) - 策略使用指南
- [数据源管理](datasource_guide.md) - 数据源使用指南
- [任务管理](task_guide.md) - 任务使用指南
- [AI 功能](ai_center_guide.md) - AI 功能使用指南
"""
    
    def save_docs(self, output_dir: str):
        """保存所有文档"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 保存完整文档
        complete_doc = self.generate_complete_doc()
        (output_path / 'admin_ui_complete_doc.md').write_text(complete_doc, encoding='utf-8')
        
        # 保存快速开始
        quick_start = self.generate_quick_start()
        (output_path / 'admin_ui_quickstart.md').write_text(quick_start, encoding='utf-8')
        
        print(f"✅ 文档已保存到：{output_path}")


def main():
    """主函数"""
    admin_ui_dir = Path(__file__).parent / 'deva' / 'admin_ui'
    output_dir = Path(__file__).parent / 'docs' / 'admin_ui'
    
    print("📝 开始生成 Admin UI 文档...")
    
    generator = AdminUIDocGenerator(admin_ui_dir)
    generator.save_docs(output_dir)
    
    print("✅ 文档生成完成！")


if __name__ == '__main__':
    main()
