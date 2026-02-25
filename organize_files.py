#!/usr/bin/env python
# coding: utf-8
"""
Deva 项目文件组织脚本

自动将根目录的文件分类整理到对应的目录中。

使用方法：
    python organize_files.py

注意：
    1. 此脚本会移动文件，请先确保已提交当前更改
    2. 运行前建议先备份重要文件
    3. 移动后会显示移动报告
"""

import os
import shutil
from pathlib import Path
from datetime import datetime


# 项目根目录
ROOT_DIR = Path(__file__).parent

# 需要创建的目录结构
DIRECTORIES = [
    "docs/reports/datasource",
    "docs/reports/ui",
    "docs/reports/integration",
    "docs/optimization",
    "docs/guides",
    "docs/api",
    "scripts/analysis",
    "scripts/demo",
    "scripts/update",
    "scripts/verify",
    "scripts/fix",
    "scripts/tools",
    "tests/unit",
    "tests/integration",
    "tests/datasource",
    "tests/ui",
    "tests/performance",
    "tests/functional",
    "tests/final",
    "archive/2025-02/datasource-fixes",
    "archive/2025-02/ui-enhancements",
    "archive/2025-02/documentation",
    "build_tools",
]

# 文件移动规则：(匹配模式，目标目录)
MOVE_RULES = [
    # 文档报告
    ("datasource_*.md", "docs/reports/datasource"),
    ("*_report.md", "docs/reports/integration"),
    ("*_REPORT.md", "docs/reports/integration"),
    ("DOCUMENTATION_*.md", "docs/optimization"),
    ("DOCUMENT_*.md", "docs/optimization"),
    
    # 分析脚本
    ("analyze_*.py", "scripts/analysis"),
    
    # 演示脚本
    ("demo_*.py", "scripts/demo"),
    
    # 更新脚本
    ("update_*.py", "scripts/update"),
    
    # 验证脚本
    ("*verification*.py", "scripts/verify"),
    ("verify_*.py", "scripts/verify"),
    
    # 修复脚本
    ("fix_*.py", "scripts/fix"),
    
    # 测试文件
    ("test_*.py", "tests"),
]

# 保留在根目录的文件（不移动）
KEEP_IN_ROOT = {
    "README.rst",
    "LICENSE",
    "requirements.txt",
    "setup.py",
    "Makefile",
    "build.sh",
    "make.bat",
    "deva.jpeg",
    "fav.png",
    "streaming.gif",
    ".gitignore",
    ".git",
    ".vscode",
    "deva",
    "source",
    "tests",
    "build",
    "dist",
    "deva.egg-info",
    ".pytest_cache",
    ".DS_Store",
}


def create_directories():
    """创建所需的目录结构"""
    print("=" * 60)
    print("创建目录结构...")
    print("=" * 60)
    
    for dir_path in DIRECTORIES:
        full_path = ROOT_DIR / dir_path
        if not full_path.exists():
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✅ 创建：{dir_path}")
        else:
            print(f"  ⏭️  已存在：{dir_path}")
    
    print()


def match_pattern(filename, pattern):
    """简单的通配符匹配"""
    import fnmatch
    return fnmatch.fnmatch(filename, pattern)


def move_files():
    """根据规则移动文件"""
    print("=" * 60)
    print("移动文件...")
    print("=" * 60)
    
    moved_files = []
    skipped_files = []
    errors = []
    
    # 获取根目录下所有文件
    root_files = [f for f in ROOT_DIR.iterdir() if f.is_file()]
    
    for file_path in root_files:
        filename = file_path.name
        
        # 检查是否应该保留在根目录
        if filename in KEEP_IN_ROOT or file_path.name.startswith('.'):
            skipped_files.append((filename, "保留在根目录"))
            continue
        
        # 检查是否已经是目录
        if file_path.is_dir():
            skipped_files.append((filename, "目录，不移动"))
            continue
        
        # 尝试匹配移动规则
        moved = False
        for pattern, target_dir in MOVE_RULES:
            if match_pattern(filename, pattern):
                target_path = ROOT_DIR / target_dir / filename
                
                # 如果目标文件已存在，添加序号
                if target_path.exists():
                    base = target_path.stem
                    ext = target_path.suffix
                    counter = 1
                    while target_path.exists():
                        target_path = ROOT_DIR / target_dir / f"{base}_{counter}{ext}"
                        counter += 1
                
                try:
                    shutil.move(str(file_path), str(target_path))
                    moved_files.append((filename, target_dir))
                    print(f"  ✅ 移动：{filename} -> {target_dir}/")
                    moved = True
                except Exception as e:
                    errors.append((filename, str(e)))
                    print(f"  ❌ 错误：{filename} - {e}")
                break
        
        # 没有匹配任何规则的文件
        if not moved and filename not in [f[0] for f in skipped_files]:
            # 移动到 archive
            archive_path = ROOT_DIR / "archive/2025-02/documentation" / filename
            try:
                shutil.move(str(file_path), str(archive_path))
                moved_files.append((filename, "archive/2025-02/documentation"))
                print(f"  📦 归档：{filename} -> archive/2025-02/documentation/")
            except Exception as e:
                errors.append((filename, str(e)))
                print(f"  ❌ 错误：{filename} - {e}")
    
    print()
    return moved_files, skipped_files, errors


def print_summary(moved_files, skipped_files, errors):
    """打印移动总结"""
    print("=" * 60)
    print("移动总结")
    print("=" * 60)
    
    print(f"\n✅ 成功移动：{len(moved_files)} 个文件")
    print(f"⏭️  跳过：{len(skipped_files)} 个文件")
    print(f"❌ 错误：{len(errors)} 个文件")
    
    if moved_files:
        print("\n📊 移动详情:")
        # 按目录分组统计
        by_dir = {}
        for filename, target_dir in moved_files:
            if target_dir not in by_dir:
                by_dir[target_dir] = []
            by_dir[target_dir].append(filename)
        
        for target_dir, files in sorted(by_dir.items()):
            print(f"\n  {target_dir}/ ({len(files)} 个文件):")
            for f in sorted(files)[:5]:  # 只显示前 5 个
                print(f"    - {f}")
            if len(files) > 5:
                print(f"    ... 还有 {len(files) - 5} 个文件")
    
    if errors:
        print("\n⚠️  错误详情:")
        for filename, error in errors:
            print(f"  - {filename}: {error}")
    
    print()


def update_gitignore():
    """更新 .gitignore 文件"""
    print("=" * 60)
    print("更新 .gitignore...")
    print("=" * 60)
    
    gitignore_path = ROOT_DIR / ".gitignore"
    
    # 要添加的内容
    additional_rules = """
# Build outputs
build/
dist/
*.egg-info/
eggs/

# Python cache
__pycache__/
*.py[cod]
*$py.class
*.so

# Testing
.pytest_cache/
.tox/
nosetests.xml
coverage.xml

# IDE
.idea/
*.swp
*.swo
*~

# OS
Thumbs.db

# Archive
archive/

# Documentation build
docs/api/_build/
"""
    
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding='utf-8')
        
        # 检查是否已存在这些规则
        if "# Build outputs" not in content:
            with open(gitignore_path, 'a', encoding='utf-8') as f:
                f.write(additional_rules)
            print("  ✅ 已更新 .gitignore")
        else:
            print("  ⏭️  .gitignore 已包含所需规则")
    else:
        gitignore_path.write_text(additional_rules, encoding='utf-8')
        print("  ✅ 已创建 .gitignore")
    
    print()


def create_readme_files():
    """创建目录索引文件"""
    print("=" * 60)
    print("创建索引文件...")
    print("=" * 60)
    
    # docs/README.md
    docs_readme = """# Deva 文档中心

## 📚 文档分类

- [reports/](reports/) - 功能实现报告
- [optimization/](optimization/) - 文档优化相关
- [guides/](guides/) - 用户指南
- [api/](api/) - API 参考

## 🔍 快速查找

### 功能报告
- 数据源自动刷新：`reports/datasource/datasource_auto_refresh_report.md`
- UI 增强集成：`reports/ui/enhanced_task_ui_integration_report.md`

### 用户指南
- 快速开始：`guides/quickstart.md`
- 安装指南：`guides/installation.md`

## 📝 文档规范

所有新增文档请遵循以下规范：
1. 使用 Markdown 格式
2. 文件名使用小写，单词间用下划线分隔
3. 在对应的分类目录下创建
4. 更新本索引文件

---

**最后更新：** """ + datetime.now().strftime("%Y-%m-%d") + """
"""
    
    docs_path = ROOT_DIR / "docs" / "README.md"
    with open(docs_path, 'w', encoding='utf-8') as f:
        f.write(docs_readme)
    print(f"  ✅ 创建：docs/README.md")
    
    # scripts/README.md
    scripts_readme = """# Deva 脚本工具集

## 📁 脚本分类

- [analysis/](analysis/) - 分析脚本
- [demo/](demo/) - 演示脚本
- [update/](update/) - 更新脚本
- [verify/](verify/) - 验证脚本
- [fix/](fix/) - 修复脚本
- [tools/](tools/) - 其他工具

## 🚀 使用示例

```bash
# 运行分析脚本
python scripts/analysis/analyze_refresh_issue.py

# 运行演示
python scripts/demo/demo_bounce_effects.py

# 运行验证
python scripts/verify/final_verification.py

# 运行修复
python scripts/fix/fix_quant_source_code.py
```

## 📝 脚本规范

所有新增脚本请遵循以下规范：
1. 使用 Python 3.8+
2. 添加完整的文档字符串
3. 在对应的分类目录下创建
4. 更新本索引文件

---

**最后更新：** """ + datetime.now().strftime("%Y-%m-%d") + """
"""
    
    scripts_path = ROOT_DIR / "scripts" / "README.md"
    with open(scripts_path, 'w', encoding='utf-8') as f:
        f.write(scripts_readme)
    print(f"  ✅ 创建：scripts/README.md")
    
    # tests/README.md
    tests_readme = """# Deva 测试套件

## 📁 测试分类

- [unit/](unit/) - 单元测试
- [integration/](integration/) - 集成测试
- [datasource/](datasource/) - 数据源测试
- [ui/](ui/) - UI 测试
- [performance/](performance/) - 性能测试
- [functional/](functional/) - 功能测试
- [final/](final/) - 最终验证

## 🚀 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定分类
pytest tests/datasource/
pytest tests/ui/

# 运行单个测试
pytest tests/datasource/test_datasource_auto_refresh.py

# 运行并生成报告
pytest tests/ --html=report.html
```

## 📝 测试规范

所有新增测试请遵循以下规范：
1. 文件名以 `test_` 开头
2. 使用 pytest 框架
3. 在对应的分类目录下创建
4. 添加完整的文档字符串

---

**最后更新：** """ + datetime.now().strftime("%Y-%m-%d") + """
"""
    
    tests_path = ROOT_DIR / "tests" / "README.md"
    with open(tests_path, 'w', encoding='utf-8') as f:
        f.write(tests_readme)
    print(f"  ✅ 创建：tests/README.md")
    
    print()


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "Deva 项目文件组织脚本" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    # 警告提示
    print("⚠️  警告：此脚本会移动文件！")
    print()
    print("在继续之前，请确保：")
    print("  1. 已提交当前所有更改到 Git")
    print("  2. 已备份重要文件")
    print("  3. 没有未保存的工作")
    print()
    
    response = input("是否继续？(输入 'yes' 继续): ")
    if response.lower() != 'yes':
        print("❌ 已取消")
        return
    
    print()
    print("开始整理文件...")
    print()
    
    # 执行整理步骤
    create_directories()
    moved_files, skipped_files, errors = move_files()
    print_summary(moved_files, skipped_files, errors)
    update_gitignore()
    create_readme_files()
    
    # 完成提示
    print("=" * 60)
    print("✅ 文件整理完成！")
    print("=" * 60)
    print()
    print("下一步：")
    print("  1. 检查移动的文件是否正确")
    print("  2. 更新文档中的引用路径")
    print("  3. 运行测试确保一切正常")
    print("  4. 提交更改到 Git")
    print()
    print("查看整理报告：")
    print(f"  - 移动了 {len(moved_files)} 个文件")
    print(f"  - 跳过了 {len(skipped_files)} 个文件")
    print(f"  - 出错了 {len(errors)} 个文件")
    print()


if __name__ == '__main__':
    main()
