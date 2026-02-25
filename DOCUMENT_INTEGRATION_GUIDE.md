# Deva 文档中心集成指南

## 📋 概述

本次集成将 Deva 的完整文档体系（包括快速开始、安装指南、使用手册、最佳实践、故障排查、API 参考等）整合到 Admin UI 的文档 Tab 中，用户可以在 Web 界面直接浏览所有文档。

---

## 🎯 集成内容

### 1. 核心文档 Tab

以下文档已集成到 Admin UI 文档 Tab 中：

| 文档 | 文件 | 说明 |
|------|------|------|
| 快速开始 | `source/quickstart.rst` | 5 分钟快速上手指南 |
| 安装指南 | `source/installation.rst` | 详细安装和配置说明 |
| 使用指南 | `source/usage.rst` | 核心功能使用方法 |
| 最佳实践 | `source/best_practices.rst` | 代码组织和性能优化建议 |
| 故障排查 | `source/troubleshooting.rst` | 常见问题和解决方案 |
| API 参考 | `source/api.rst` | 完整 API 文档 |
| 术语表 | `source/glossary.rst` | 技术术语解释 |

### 2. 示例文档 Tab

- 集成 `deva/examples/README.md`
- 包含所有示例的分类说明
- 按场景查找指南
- 学习路径建议

### 3. 模块 API 文档 Tab

自动扫描以下模块并生成文档：

- `core` - 核心流处理
- `pipe` - 管道操作
- `store` - 存储
- `sources` - 数据源
- `when` - 定时和调度
- `namespace` - 命名空间
- `bus` - 消息总线
- `endpoints` - 输出端
- `compute` - 计算算子
- `search` - 全文检索
- `browser` - 浏览器
- `page` - 页面服务
- `lambdas` - Lambda 函数
- `admin` - 管理功能
- `llm` - LLM 集成
- `admin_ui` - 管理界面
- `page_ui` - 页面 UI

### 4. 文档优化报告 Tab

- 集成 `DOCUMENTATION_OPTIMIZATION_SUMMARY.md`
- 显示文档优化工作总结
- 包含改进指标和后续建议

---

## 🚀 使用方法

### 方式 1：通过 Admin UI 访问

1. **启动 Deva Admin**

```python
from deva.admin import admin
admin()
```

2. **访问 Admin UI**

浏览器打开：`http://127.0.0.1:9999`

3. **点击导航菜单中的【文档】选项卡**

4. **浏览文档内容**

文档中心会显示所有可用的文档 Tab，点击切换查看。

### 方式 2：使用测试脚本

```bash
python3 test_document_integration.py
```

### 方式 3：在代码中调用

```python
from deva.admin_ui.document import render_document_ui

# 在 PyWebIO 上下文中调用
render_document_ui(ctx)
```

---

## 📊 文档渲染效果

### RST 文档渲染

- 使用 `docutils` 将 RST 转换为 HTML
- 支持代码高亮
- 支持表格、列表等格式
- 支持图片显示
- 自动添加样式优化阅读体验

### Markdown 文档渲染

- 简单 Markdown 语法转换
- 支持标题、粗体、代码块
- 支持链接和列表
- 自动添加样式

### 模块 API 文档

- 自动扫描模块成员
- 显示函数/类的文档字符串
- 提取代码样例
- 支持在线测试函数

---

## 🔧 技术实现

### 文档加载流程

```python
# 1. 扫描 source 目录
documents = _load_all_documents()

# 2. 读取 RST 文件
text, path = _load_document_file("quickstart.rst")

# 3. 渲染为 HTML
html_body, error = _render_rst_to_html(text, path)

# 4. 构建 Tab
tab = _build_document_tab(ctx, filename, doc_info)

# 5. 添加到 Tabs 列表
tabs.append(tab)
```

### 样式优化

```css
.admin-rst-doc {
  max-width: 980px;
  margin: 0 auto;
  line-height: 1.8;
  font-size: 15px;
  color: #222;
}

.admin-rst-doc code {
  background: #f6f8fa;
  padding: 1px 4px;
  border-radius: 4px;
}

.admin-rst-doc pre {
  background: #f6f8fa;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
}
```

---

## 📁 文件结构

```
deva/
├── source/                          # Sphinx 文档源文件
│   ├── quickstart.rst               # ✅ 已集成
│   ├── installation.rst             # ✅ 已集成
│   ├── usage.rst                    # ✅ 已集成
│   ├── best_practices.rst           # ✅ 已集成
│   ├── troubleshooting.rst          # ✅ 已集成
│   ├── api.rst                      # ✅ 已集成
│   ├── glossary.rst                 # ✅ 已集成
│   ├── manual_cn.rst                # ✅ 已集成
│   └── index.rst                    # Sphinx 索引
├── deva/
│   ├── examples/
│   │   └── README.md                # ✅ 已集成
│   └── admin_ui/
│       └── document.py              # 文档 UI 渲染逻辑
├── DOCUMENTATION_OPTIMIZATION_SUMMARY.md  # ✅ 已集成
└── test_document_integration.py     # 测试脚本
```

---

## 🎨 UI 界面

### 文档中心首页

```
┌─────────────────────────────────────────────┐
│  📚 Deva 文档中心                            │
│  本文档中心包含快速开始、安装指南、使用手册  │
│  最佳实践、故障排查等完整文档。              │
│                                             │
│  [🔄 刷新文档缓存]                          │
├─────────────────────────────────────────────┤
│ [快速开始] [安装指南] [使用指南] [最佳实践] │
│ [故障排查] [API 参考] [术语表] [示例文档]  │
│ [core] [pipe] [store] [sources] [when] ... │
│ [文档优化报告]                              │
└─────────────────────────────────────────────┘
```

### 文档内容区域

```
┌─────────────────────────────────────────────┐
│  快速开始                                   │
│  来源：/path/to/source/quickstart.rst       │
├─────────────────────────────────────────────┤
│                                             │
│  5 分钟快速上手 Deva                         │
│                                             │
│  步骤 1：安装 Deva                           │
│  pip install deva                           │
│                                             │
│  步骤 2：创建第一个流                        │
│  [代码示例...]                              │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 🔍 功能特性

### 1. 文档缓存

- 使用缓存避免重复加载
- 默认缓存 TTL：300 秒
- 支持手动刷新缓存

### 2. 错误处理

- RST 渲染失败时降级显示源码
- 文件不存在时显示友好提示
- 异常信息格式化显示

### 3. 响应式设计

- 自适应不同屏幕尺寸
- 移动端友好
- 代码块横向滚动

### 4. 代码高亮

- Python 语法高亮
- 行号和折叠（可选）
- 复制按钮（可选）

---

## 🛠️ 自定义和扩展

### 添加新文档

1. **在 source 目录创建 RST 文件**

```rst
新文档.rst
==========

内容...
```

2. **在 `_load_all_documents` 函数中注册**

```python
doc_files = [
    ("quickstart.rst", "快速开始"),
    ("新文档.rst", "新文档标题"),  # 添加这行
]
```

3. **刷新 Admin UI 即可看到新文档**

### 自定义样式

在 `_build_document_tab` 函数中修改 CSS：

```python
doc_style = """
<style>
  .admin-rst-doc {
    /* 自定义样式 */
  }
</style>
"""
```

### 添加自定义 Tab

```python
def _build_custom_tab(ctx):
    return {
        "title": "自定义文档",
        "content": ctx["put_html"]("<div>内容</div>"),
    }

# 在 render_document_ui 中添加
tabs.append(_build_custom_tab(ctx))
```

---

## 📝 使用技巧

### 1. 快速查找文档

- 使用浏览器的页面搜索功能（Ctrl+F）
- 利用术语表查找专业术语
- 通过目录快速定位

### 2. 代码示例测试

- 点击模块文档中的【执行测试】按钮
- 查看函数执行结果
- 对比文档样例

### 3. 文档缓存管理

- 文档更新后点击【刷新文档缓存】
- 修改默认缓存时间：

```python
ctx['cache_ttl'] = 600  # 10 分钟
```

---

## ❓ 常见问题

### Q: 文档显示乱码？

**A:** 确保文件编码为 UTF-8，检查系统 locale 设置。

### Q: RST 渲染失败？

**A:** 安装 docutils：

```bash
pip install docutils
```

### Q: 文档更新后没有变化？

**A:** 点击【刷新文档缓存】按钮，或重启 Admin UI。

### Q: 如何查看文档源文件？

**A:** 每个文档 Tab 底部都显示了源文件路径，可以直接打开查看。

### Q: 移动端访问显示异常？

**A:** 文档已适配移动端，建议使用现代浏览器（Chrome、Safari）。

---

## 📈 性能优化

### 1. 懒加载

文档按需加载，避免一次性加载所有文档。

### 2. 缓存策略

```python
# 调整缓存时间
ctx['cache_ttl'] = 600  # 10 分钟
```

### 3. 异步加载

对于大型文档，可以考虑异步加载：

```python
async def load_large_doc(ctx):
    # 异步加载逻辑
    pass
```

---

## 🎯 最佳实践

### 文档编写

1. **使用标准 RST 语法**
2. **提供代码示例**
3. **添加清晰的标题层级**
4. **使用表格和列表增强可读性**

### 文档维护

1. **定期更新文档内容**
2. **保持文档与代码同步**
3. **收集用户反馈改进文档**
4. **建立文档审查流程**

### 文档组织

1. **按功能模块组织文档**
2. **提供清晰的导航结构**
3. **添加交叉引用**
4. **维护术语表**

---

## 🔗 相关资源

- [Sphinx 文档](https://www.sphinx-doc.org/)
- [RST 语法](https://docutils.sourceforge.io/rst.html)
- [PyWebIO 文档](https://pywebio.readthedocs.io/)
- [Docutils 文档](https://docutils.sourceforge.io/)

---

## 📞 反馈与支持

如有问题或建议，请：

1. 提交 GitHub Issue
2. 联系项目维护者
3. 提交 Pull Request 改进文档

---

**最后更新：** 2026-02-26  
**文档版本：** Deva v1.0  
**维护者：** Deva 团队
