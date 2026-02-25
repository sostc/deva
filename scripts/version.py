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
    python scripts/version.py release   # 完整发布流程

示例：
    python scripts/version.py bump patch
    python scripts/version.py tag
    python scripts/version.py release
"""

import re
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

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


def check_git_status():
    """检查 Git 状态"""
    result = subprocess.run(['git', 'status', '--porcelain'], 
                          capture_output=True, text=True)
    if result.stdout.strip():
        print("⚠️  警告：工作目录有未提交的更改")
        print(result.stdout)
        response = input("是否继续？(y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    return True


def check_tests():
    """运行测试检查"""
    print("🧪 运行测试...")
    result = subprocess.run(['python', '-m', 'pytest', 'tests/', '-q', '--tb=no'])
    if result.returncode != 0:
        print("⚠️  警告：部分测试未通过")
        response = input("是否继续发布？(y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    else:
        print("✅ 所有测试通过")
    return True


def build_package():
    """构建分发包"""
    print("📦 构建分发包...")
    
    # 清理旧的构建文件
    dist_dir = ROOT / 'dist'
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    
    # 构建
    result = subprocess.run(['python', 'setup.py', 'sdist', 'bdist_wheel'])
    if result.returncode != 0:
        print("❌ 构建失败")
        sys.exit(1)
    
    print("✅ 构建完成")
    return True


def create_tag(version):
    """创建 Git Tag"""
    tag_name = f'v{version}'
    
    # 检查 Tag 是否已存在
    result = subprocess.run(['git', 'tag', '-l', tag_name], 
                          capture_output=True, text=True)
    if result.stdout.strip():
        print(f"⚠️  警告：Tag {tag_name} 已存在")
        response = input("是否删除并重新创建？(y/n): ")
        if response.lower() == 'y':
            subprocess.run(['git', 'tag', '-d', tag_name])
            subprocess.run(['git', 'push', 'origin', '--delete', tag_name], 
                         capture_output=True)
        else:
            sys.exit(0)
    
    # 创建带注解的 Tag
    subprocess.run(['git', 'tag', '-a', tag_name, '-m', f'Release version {version}'])
    print(f'✅ 已创建 Tag: {tag_name}')
    
    # 推送 Tag
    print('\n提示：运行以下命令推送到远程')
    print(f'  git push origin {tag_name}')
    print(f'  git push origin --tags')
    
    return True


def push_to_remote(tag_name):
    """推送到远程仓库"""
    print("🚀 推送到远程仓库...")
    
    # 推送提交
    result = subprocess.run(['git', 'push', 'origin', 'master'])
    if result.returncode != 0:
        print("❌ 推送提交失败")
        return False
    
    # 推送 Tag
    result = subprocess.run(['git', 'push', 'origin', tag_name])
    if result.returncode != 0:
        print("❌ 推送 Tag 失败")
        return False
    
    print("✅ 推送成功")
    return True


def publish_to_pypi():
    """发布到 PyPI"""
    print("📤 发布到 PyPI...")
    
    if not shutil.which('twine'):
        print("⚠️  未安装 twine，请先安装：pip install twine")
        return False
    
    # 上传
    result = subprocess.run(['twine', 'upload', 'dist/*'])
    if result.returncode != 0:
        print("❌ 发布失败")
        return False
    
    print("✅ 发布成功")
    return True


def release():
    """完整的发布流程"""
    print("=" * 60)
    print("🚀 Deva 版本发布流程")
    print("=" * 60)
    print()
    
    # 1. 检查 Git 状态
    check_git_status()
    
    # 2. 运行测试
    check_tests()
    
    # 3. 升级版本号
    print("\n当前版本:", get_version())
    print("请选择要升级的版本类型:")
    print("  1) major (主版本号，不兼容变更)")
    print("  2) minor (次版本号，新功能)")
    print("  3) patch (修订号，Bug 修复)")
    
    choice = input("\n请选择 (1/2/3): ")
    level_map = {'1': 'major', '2': 'minor', '3': 'patch'}
    level = level_map.get(choice)
    
    if not level:
        print("❌ 无效选择")
        sys.exit(1)
    
    new_version = bump_version(level)
    print(f"✅ 新版本：{new_version}")
    
    # 4. 提交更改
    print("\n📝 提交版本更新...")
    subprocess.run(['git', 'add', str(INIT_PY), str(SETUP_PY), str(CHANGELOG)])
    subprocess.run(['git', 'commit', '-m', f'release: 发布版本 {new_version}'])
    
    # 5. 创建 Tag
    tag_name = f'v{new_version}'
    create_tag(new_version)
    
    # 6. 构建
    build_package()
    
    # 7. 推送
    push_to_remote(tag_name)
    
    # 8. 发布到 PyPI（可选）
    response = input("\n是否发布到 PyPI? (y/n): ")
    if response.lower() == 'y':
        publish_to_pypi()
    
    # 完成
    print("\n" + "=" * 60)
    print(f"✅ 版本 {new_version} 发布完成！")
    print("=" * 60)
    print(f"\n新版本：{new_version}")
    print(f"Git Tag: {tag_name}")
    print(f"变更日志：CHANGELOG.md")


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
        print('\n记得提交更改并创建 Tag:')
        print(f'  git add deva/__init__.py setup.py')
        print(f'  git commit -m "release: 发布版本 {new_version}"')
        print(f'  git tag -a v{new_version} -m "Release version {new_version}"')
        print(f'  git push origin master v{new_version}')
    
    elif command == 'tag':
        version = get_version()
        create_tag(version)
    
    elif command == 'release':
        release()
    
    else:
        print(f'未知命令：{command}')
        sys.exit(1)


if __name__ == '__main__':
    main()
