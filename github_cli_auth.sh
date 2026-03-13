#!/bin/bash

# GitHub CLI 认证脚本

# 设置代理
export https_proxy=http://127.0.0.1:6152
export http_proxy=http://127.0.0.1:6152
export all_proxy=socks5://127.0.0.1:6153

echo '=== GitHub CLI 认证指南 ==='
echo ''
echo '步骤 1: 生成 GitHub 个人访问令牌 (PAT)'
echo '1. 打开浏览器访问: https://github.com/settings/tokens'
echo '2. 点击 "Generate new token"'
echo '3. 选择 "Generate new token (classic)"'
echo '4. 输入描述信息，例如 "GitHub CLI Authentication"'
echo '5. 选择所需权限（建议至少选择 repo 权限）'
echo '6. 点击 "Generate token"'
echo '7. 复制生成的令牌，妥善保存'
echo ''
echo '步骤 2: 执行认证命令'
echo '将 <YOUR_TOKEN> 替换为您刚才生成的令牌，然后运行以下命令:'
echo ''
echo '   export https_proxy=http://127.0.0.1:6152; export http_proxy=http://127.0.0.1:6152; export all_proxy=socks5://127.0.0.1:6153; echo "<YOUR_TOKEN>" | gh auth login --with-token'
echo ''
echo '步骤 3: 验证认证状态'
echo '认证完成后，运行以下命令验证:'
echo ''
echo '   export https_proxy=http://127.0.0.1:6152; export http_proxy=http://127.0.0.1:6152; export all_proxy=socks5://127.0.0.1:6153; gh auth status'
echo ''
echo '=== 认证完成 ==='
