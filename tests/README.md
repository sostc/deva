# Deva 测试套件

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

**最后更新：** 2026-02-26
