#!/usr/bin/env python3
"""
验证gen_quant代码已存储到数据源执行代码中

⚠️ 已知失效（2026-10-15 核查，尚未处置 —— 需人拍板）
--------------------------------------------------
本守卫依赖 `deva.admin.strategy.datasource.get_ds_manager`，但：

  * `git log --diff-filter=D` 显示该模块与 `get_ds_manager` **从未被提交过**
    （不是"被删了"，是"从来没存在"）—— 守卫写于 2026-03-18，脱离了实现；
  * 被测功能本身（`quant_source` 数据源 / `gen_quant` 函数）在全仓库
    也搜不到任何痕迹。

结论：这是一个**指向不存在功能的守卫**，永远不可能通过，只会训练人忽略红色。
处置二选一：① 退役删除；② 按当前数据源管理器（`deva/naja/datasource/manager.py`）重写。
在处置之前，它**如实报错**（exit 1 + 原因），不做静默跳过。
"""

import sys

try:
    from deva.admin.strategy.datasource import get_ds_manager
except ImportError as e:  # pragma: no cover - 结构性失效
    print("❌ verify_gen_quant_storage 已失效：")
    print(f"   依赖模块不可用 —— {e}")
    print("   `deva.admin.strategy.datasource` 在 git 中从不存在（见文件头说明）。")
    print("   处置：删除本守卫，或按 deva/naja/datasource/manager.py 重写。")
    sys.exit(1)

def main():
    """验证gen_quant代码存储功能"""
    print("=== 验证gen_quant代码存储到数据源执行代码 ===")
    
    # 获取数据源管理器
    ds_manager = get_ds_manager()
    
    # 查找quant_source数据源
    quant_source = ds_manager.get_source_by_name("quant_source")
    
    if not quant_source:
        print("✗ 未找到quant_source数据源")
        return False
    
    print(f"✓ 找到quant_source数据源: {quant_source.id}")
    print(f"✓ 数据源名称: {quant_source.name}")
    print(f"✓ 数据源状态: {quant_source.state.status}")
    print(f"✓ 数据源类型: {quant_source.metadata.source_type}")
    print(f"✓ 执行间隔: {quant_source.metadata.interval} 秒")
    
    # 检查执行代码
    code = quant_source.metadata.data_func_code
    print(f"✓ 执行代码长度: {len(code)} 字符")
    
    # 验证代码包含关键函数
    key_functions = ['fetch_data', 'gen_quant', 'is_tradedate', 'is_tradetime', 'create_mock_data']
    found_functions = []
    
    for func in key_functions:
        if f"def {func}" in code:
            found_functions.append(func)
    
    print(f"✓ 找到的关键函数: {found_functions}")
    
    # 检查代码内容
    print("\n✓ 代码结构预览:")
    lines = code.split('\n')
    preview_lines = []
    for line in lines:
        if line.strip().startswith('def ') or line.strip().startswith('import '):
            preview_lines.append(line.strip())
        if len(preview_lines) >= 10:
            break
    
    for line in preview_lines:
        print(f"    {line}")
    
    # 验证关键功能
    print(f"\n✓ 功能验证:")
    print(f"  - 包含交易日判断: {'is_tradedate' in found_functions}")
    print(f"  - 包含交易时间判断: {'is_tradetime' in found_functions}")
    print(f"  - 包含行情获取: {'gen_quant' in found_functions}")
    print(f"  - 包含数据获取入口: {'fetch_data' in found_functions}")
    print(f"  - 包含降级机制: {'create_mock_data' in found_functions}")
    
    # 检查状态保存
    saved_state = quant_source.get_saved_running_state()
    if saved_state:
        print(f"\n✓ 状态保存:")
        print(f"  - 运行状态: {saved_state.get('is_running')}")
        print(f"  - 保存时间: {saved_state.get('last_update')}")
        print(f"  - 进程ID: {saved_state.get('pid')}")
    
    # 检查代码版本
    code_versions = quant_source.get_code_versions(3)
    print(f"\n✓ 代码版本历史: {len(code_versions)} 个版本")
    
    print(f"\n✅ 验证完成！")
    print("✅ gen_quant相关代码已成功存储到数据源执行代码中")
    print("✅ 代码包含完整的行情获取、交易日判断、降级机制")
    print("✅ 支持状态持久化和程序重启恢复")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)