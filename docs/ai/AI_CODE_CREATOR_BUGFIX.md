# AI 代码创建器 Bug 修复报告

## 修复日期
2026-02-26

## 问题概述
AI 代码创建器功能存在多个 bug，导致无法正常使用。

## 修复的问题

### 1. Tab 切换问题
**问题**: `put_tabs()` 无法序列化函数对象
**错误**: `TypeError: Object of type function is not JSON serializable`

**修复方案**:
- 改用按钮 + scope 的方式实现 Tab 切换
- 使用 `ctx['ai_current_tab']` 跟踪当前 Tab
- 通过 `switch_tab()` 异步函数切换内容

**修改文件**: `deva/admin/ai_center.py`

### 2. 数据源保存问题
**问题**: 
- `save_datasource()` 中 `config.get('type')` 应该是 `config.get('source_type')`
- `interval` 参数可能不是有效的 float
- 保存成功后没有关闭弹窗

**修复方案**:
```python
# 修复类型映射
source_type_str = config.get('source_type', 'custom')

# 安全转换 interval
try:
    interval = float(config.get('interval', 5.0))
except (ValueError, TypeError):
    interval = 5.0

# 关闭弹窗
if close_popup:
    close_popup()
```

**修改文件**: `deva/admin/ai_code_creator.py`

### 3. 最近创建记录刷新问题
**问题**: `add_to_recent_creations()` 是同步函数但需要异步刷新 UI

**修复方案**:
- 将函数改为异步：`async def add_to_recent_creations()`
- 添加异常处理避免刷新失败导致整个流程中断
- 所有调用处添加 `await`

**修改文件**: `deva/admin/ai_code_creator.py`

### 4. 保存策略和任务的问题
**问题**: 
- `save_strategy()` 和 `save_task()` 没有使用 `await` 调用 `add_to_recent_creations()`
- 保存成功后没有关闭弹窗

**修复方案**:
```python
# 添加 await
await add_to_recent_creations(ctx, {...})

# 关闭弹窗
if close_popup:
    close_popup()
```

**修改文件**: `deva/admin/ai_code_creator.py`

## 修复详情

### ai_center.py 修改
```python
# 之前 - 使用 put_tabs 传递函数
put_tabs([
    {'title': '💬 智能对话', 'content': lambda: run_async(show_ai_chat(ctx))},
    ...
])

# 之后 - 使用按钮切换
async def switch_tab(tab_name):
    ctx['ai_current_tab'] = tab_name
    ctx['clear']('ai_tab_content')
    with ctx['use_scope']('ai_tab_content'):
        if tab_name == 'chat':
            run_async(show_ai_chat(ctx))
        ...
```

### ai_code_creator.py 修改

#### 1. save_datasource()
```python
# 修复前
source_type=type_map.get(config.get('type', 'custom'), ...)
interval=float(config.get('interval', 5.0))

# 修复后
source_type_str = config.get('source_type', 'custom')
source_type=type_map.get(source_type_str, ...)
try:
    interval = float(config.get('interval', 5.0))
except (ValueError, TypeError):
    interval = 5.0
```

#### 2. add_to_recent_creations()
```python
# 修复前
def add_to_recent_creations(ctx, item: dict):
    ...
    ctx['clear']('recent_creations')  # 可能失败

# 修复后
async def add_to_recent_creations(ctx, item: dict):
    ...
    try:
        ctx['clear']('recent_creations')
        with ctx['use_scope']('recent_creations'):
            show_recent_creations(ctx)
    except Exception:
        pass  # 忽略刷新错误
```

#### 3. save_strategy() 和 save_task()
```python
# 修复前
add_to_recent_creations(ctx, {...})  # 缺少 await

# 修复后
await add_to_recent_creations(ctx, {...})
```

## 测试验证

### 导入测试
```bash
cd /Users/spark/pycharmproject/deva
python -c "from deva.admin import ai_code_creator; print('OK')"
```
结果：✅ 通过

### 功能测试
1. ✅ AI Tab 页面可以正常打开
2. ✅ Tab 切换功能正常
3. ✅ 数据源创建器可以打开
4. ✅ 代码生成功能正常
5. ✅ 保存功能逻辑正确

## 遗留问题

### 1. 策略保存
- 当前策略创建后只保存代码到临时记录
- 需要手动前往策略管理页面创建
- **原因**: 策略创建需要配置数据源、参数等，逻辑较复杂

### 2. 任务保存
- 当前任务创建后只保存代码到临时记录
- 需要手动前往任务管理页面创建
- **原因**: 任务调度需要 APScheduler 集成

### 3. 代码编辑
- 生成的代码无法在线编辑
- 需要复制后在外部编辑器修改
- **计划**: 后续添加在线代码编辑器

## 改进建议

### 短期改进
1. ✅ 修复所有异步调用问题
2. ✅ 添加异常处理
3. ⏳ 添加代码预览功能
4. ⏳ 优化错误提示信息

### 长期改进
1. 添加代码编辑器（Monaco Editor）
2. 支持代码版本管理
3. 支持一键部署到生产环境
4. 添加代码模板库
5. 支持批量创建和导入导出

## 文件清单

### 修改的文件
1. `deva/admin/ai_center.py` - Tab 切换逻辑
2. `deva/admin/ai_code_creator.py` - 代码创建逻辑

### 新增的文件
1. `AI_CODE_CREATOR_GUIDE.md` - 使用指南
2. `AI_CODE_CREATOR_BUGFIX.md` - 本文档

## 总结

本次修复解决了 AI 代码创建器的主要功能 bug，包括：
- ✅ Tab 切换功能
- ✅ 数据源保存
- ✅ 异步调用
- ✅ 异常处理

现在用户可以：
1. 正常使用 AI 代码创建器
2. 生成数据源、策略、任务代码
3. 一键保存数据源到数据库
4. 查看最近创建记录

后续将继续优化用户体验，添加更多实用功能。
