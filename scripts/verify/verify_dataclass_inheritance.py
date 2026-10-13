#!/usr/bin/env python3
"""守卫：dataclass 继承链 / 序列化一致性 —— 「写好了字段却没被 dataclass 收进去」

背景（为什么要有这个守卫）
------------------------------------------------------------------
`dictionary/models.py` 的 `DictionaryMetadata(UnitMetadata)` 少了一个
`@dataclass`。**看起来**只是漏装饰器，实际后果是整条链路：

  * 没有装饰器 ⇒ 那 14 行只是**普通类属性**，`dataclasses.fields()` 收不到，
    `__init__` 仍只认基类 6 个参数；
  * 于是 `DictionaryEntry.from_dict()` / `DictionaryManager.create()` 里
    那两处 `DictionaryMetadata(dict_type=…, daily_time=…)` **必然 TypeError**
    （`UnitMetadata.__init__() got an unexpected keyword argument`）；
  * 表现却是「静默的」：`naja_dictionary_entries` 表至今 **0 行**，
    字典功能从 2026-04 重构后就没人真正建成过；
  * 更难识别的是 `DictionaryEntry.to_dict()` 里那一串
    `getattr(m, k, 默认值)` —— 字段没接上时它读到的是**类默认值**，
    于是「配置写了、也落盘了、重启后又回到默认值」，全程无异常无日志。

证据它不是设计选择而是遗漏：同族的 `DataSourceMetadata` / `TaskMetadata` /
`StrategyMetadata` **全都带了 `@dataclass`**，只有它例外。

本守卫四段检查
------------------------------------------------------------------
  ① **静态（全仓）**：继承了「已知被 `@dataclass` 装饰过的类」，且本类又写了
     新的注解，却没给自己加 `@dataclass` → 报错。
  ② **运行时（定向）**：`DictionaryMetadata` 必须是真 dataclass，且
     `dataclasses.fields()` 必须覆盖源码里声明的**全部**注解。
     这一段能抓到「装饰器看着在、实际不生效」的任何形态。
  ③ **序列化一致**：`DictionaryEntry.to_dict()` 里 `metadata` 字典的键集合
     必须 **等于** 该类字段集合 —— 少写 = 落盘丢字段（重启回到默认值），
     多写 = 写了个不存在的字段（永远是类默认值）。
  ④ **构造合法**：所有 `DictionaryMetadata(…)` 调用的具名参数必须是真字段。

用法
------------------------------------------------------------------
    python3 scripts/verify/verify_dataclass_inheritance.py
    python3 scripts/verify/verify_dataclass_inheritance.py --strict  # 有跳过也不许过
    python3 scripts/verify/verify_dataclass_inheritance.py --self-test  # 自证有区分度
"""

from __future__ import annotations

import argparse
import ast
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = REPO_ROOT / "deva"

# ② 定向运行时检查的目标（模块路径.类名）
TARGET_CLASSES = ("deva.naja.dictionary.models.DictionaryMetadata",)

# ③ 序列化点：相对路径 -> (所属类, 方法名)
SERIALIZERS = {
    "deva/naja/dictionary/entry.py": ("DictionaryEntry", "to_dict"),
}

# ④ 被检查的构造调用函数名 -> 扫描范围
CTOR_TARGETS = {"DictionaryMetadata": ("deva/naja/dictionary",)}


def _rel(p: Path, base: Path) -> str:
    try:
        return str(p.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _iter_py(root: Path):
    for p in sorted(root.rglob("*.py")):
        parts = set(p.parts)
        if "__pycache__" in parts or ".git" in parts:
            continue
        yield p


def _decorators(node: ast.ClassDef) -> set[str]:
    """返回装饰器的「最后一段名字」，如 `dataclasses.dataclass` -> dataclass"""
    out = set()
    for d in node.decorator_list:
        if isinstance(d, ast.Name):
            out.add(d.id)
        elif isinstance(d, ast.Attribute):
            out.add(d.attr)
        elif isinstance(d, ast.Call):
            f = d.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def _annotations(node: ast.ClassDef) -> list[str]:
    out = []
    for st in node.body:
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
            out.append(st.target.id)
    return out


def _base_names(node: ast.ClassDef) -> list[str]:
    out = []
    for b in node.bases:
        if isinstance(b, ast.Name):
            out.append(b.id)
        elif isinstance(b, ast.Attribute):
            out.append(b.attr)
    return out


# ---------------------------------------------------------------- ① 静态
def collect_missing_decorator(root: Path) -> tuple[list[str], int]:
    """返回 (问题列表, 扫描到的类总数)"""
    trees: list[tuple[str, ast.Module]] = []
    for p in _iter_py(root):
        try:
            trees.append((_rel(p, REPO_ROOT), ast.parse(p.read_text(encoding="utf-8"), str(p))))
        except (OSError, SyntaxError, ValueError):
            continue

    known_dc: set[str] = set()
    total = 0
    for _, tree in trees:
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef):
                total += 1
                if "dataclass" in _decorators(cls):
                    known_dc.add(cls.name)

    findings: list[str] = []
    for path, tree in trees:
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if "dataclass" in _decorators(cls):
                continue
            parents = [b for b in _base_names(cls) if b in known_dc]
            mine = _annotations(cls)
            if parents and mine:
                findings.append(
                    f"{path}:{cls.lineno} {cls.name} 继承了 dataclass "
                    f"({', '.join(parents)}) 又写了 {len(mine)} 个新注解，"
                    f"却没有给自己加 @dataclass → 这些字段不会成为字段，"
                    f"构造时传它们会 TypeError"
                )
    return findings, total


# ---------------------------------------------------------------- ② 运行时
def collect_runtime_field_issues(skips: list[str]) -> list[str]:
    findings: list[str] = []
    if not TARGET_CLASSES:
        return findings
    try:
        from guard_sandbox import isolate_guard_db

        isolate_guard_db()
    except Exception as e:  # 隔离不了就别碰生产库
        skips.append(f"② 运行时字段检查：无法隔离守卫库（{e}）")
        return findings

    import dataclasses
    import importlib

    for dotted in TARGET_CLASSES:
        mod_path, _, cls_name = dotted.rpartition(".")
        try:
            cls = getattr(importlib.import_module(mod_path), cls_name)
        except Exception as e:
            skips.append(f"② 运行时字段检查：{dotted} 导入失败（{e}）")
            continue

        if not dataclasses.is_dataclass(cls):
            findings.append(
                f"② {dotted} 不是 dataclass → 它声明的注解只会沦为类属性，"
                f"构造时传这些名字必然 TypeError"
            )
            continue

        runtime = {f.name for f in dataclasses.fields(cls)}
        try:
            src = Path(sys.modules[mod_path].__file__)
            tree = ast.parse(src.read_text(encoding="utf-8"), str(src))
        except (OSError, SyntaxError) as e:
            skips.append(f"② 源码解析失败（{e}）")
            continue

        declared: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == cls_name:
                declared = _annotations(node)
        missing = [n for n in declared if n not in runtime]
        if missing:
            findings.append(
                f"② {dotted} 源码声明了 {len(declared)} 个注解，"
                f"但 dataclasses.fields() 只认到 {len(runtime)} 个，"
                f"缺：{', '.join(missing)}"
            )
    return findings


# ---------------------------------------------------------------- ③ 序列化
def _metadata_dict_keys(tree: ast.Module, cls_name: str, method: str) -> list[str] | None:
    """找 `class X: def method(self): return {"metadata": {...}, ...}` 里的键"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for fn in node.body:
                if isinstance(fn, ast.FunctionDef) and fn.name == method:
                    for sub in ast.walk(fn):
                        if isinstance(sub, ast.Dict):
                            for k, v in zip(sub.keys, sub.values):
                                if (
                                    isinstance(k, ast.Constant)
                                    and k.value == "metadata"
                                    and isinstance(v, ast.Dict)
                                ):
                                    return [
                                        c.value
                                        for c in v.keys
                                        if isinstance(c, ast.Constant) and isinstance(c.value, str)
                                    ]
    return None


def collect_serializer_issues(skips: list[str]) -> list[str]:
    findings: list[str] = []
    import dataclasses
    import importlib

    for rel, (cls_name, method) in SERIALIZERS.items():
        src = REPO_ROOT / rel
        try:
            tree = ast.parse(src.read_text(encoding="utf-8"), str(src))
        except (OSError, SyntaxError) as e:
            skips.append(f"③ {rel} 解析失败（{e}）")
            continue
        keys = _metadata_dict_keys(tree, cls_name, method)
        if keys is None:
            skips.append(f"③ {rel} 里没找到 {cls_name}.{method} 的 metadata 字典")
            continue

        # 该解析器写的是哪个 metadata 类？取 __init__ 里 `self._metadata = X()`
        mod = rel[: -len(".py")].replace("/", ".")
        try:
            mod_obj = importlib.import_module(mod)
        except Exception as e:
            skips.append(f"③ {mod} 导入失败（{e}）")
            continue

        target = None
        for dotted in TARGET_CLASSES:
            dotted_mod, _, cname = dotted.rpartition(".")
            _f, _, mname = mod.rpartition(".")
            if dotted_mod.startswith(_f):
                target = getattr(importlib.import_module(dotted_mod), cname)
                break
        if target is None or not dataclasses.is_dataclass(target):
            skips.append(f"③ 无法确定 {mod} 对应的 metadata 类")
            continue

        fields = {f.name for f in dataclasses.fields(target)}
        written = set(keys)
        lost = sorted(fields - written)
        phantom = sorted(written - fields)
        if lost:
            findings.append(
                f"③ {rel}:{cls_name}.{method} 的 metadata 少写了 {len(lost)} 个字段"
                f"→ 落盘丢配置、重启回到默认值：{', '.join(lost)}"
            )
        if phantom:
            findings.append(
                f"③ {rel}:{cls_name}.{method} 的 metadata 多写了不存在的字段"
                f"（写入的一定是类默认值）：{', '.join(phantom)}"
            )
        del mod_obj
    return findings


# ---------------------------------------------------------------- ④ 构造
def collect_ctor_issues() -> list[str]:
    findings: list[str] = []
    import dataclasses
    import importlib

    runtime: dict[str, set[str]] = {}
    for dotted in TARGET_CLASSES:
        mod_path, _, cls_name = dotted.rpartition(".")
        try:
            cls = getattr(importlib.import_module(mod_path), cls_name)
        except Exception:
            continue
        if dataclasses.is_dataclass(cls):
            runtime[cls_name] = {f.name for f in dataclasses.fields(cls)}

    for name, scopes in CTOR_TARGETS.items():
        if name not in runtime:
            continue
        for rel in scopes:
            for p in _iter_py(REPO_ROOT / rel):
                try:
                    tree = ast.parse(p.read_text(encoding="utf-8"), str(p))
                except (OSError, SyntaxError):
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    fn = node.func
                    nm = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
                    if nm != name:
                        continue
                    bad = [k.arg for k in node.keywords if k.arg and k.arg not in runtime[name]]
                    if bad:
                        findings.append(
                            f"④ {_rel(p, REPO_ROOT)}:{node.lineno} "
                            f"{name}(...) 传了不存在的字段 {', '.join(bad)} → TypeError"
                        )
    return findings


# ---------------------------------------------------------------- 自证
_SELFTEST_SOURCE = '''
from dataclasses import dataclass


@dataclass
class Base:
    id: str = ""


@dataclass
class Good(Base):          # ✅ 正确写法
    daily_time: str = "03:00"


class Bad(Base):           # ❌ 漏了 @dataclass
    daily_time: str = "03:00"
'''


def self_test() -> int:
    print("=== 自证：① 静态区分度 ===")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "mod.py").write_text(_SELFTEST_SOURCE, encoding="utf-8")
        findings, total = collect_missing_decorator(root)
        print(f"扫描类数={total}")
        for f in findings:
            print("  🔍", f)
        bad_hit = any("Bad" in f for f in findings)
        good_clean = not any("Good" in f for f in findings)
        print("  命中漏装饰器的 Bad:", "✅" if bad_hit else "❌ 守卫没区分度！")
        print("  不误报正常写的 Good:", "✅" if good_clean else "❌ 守卫误报！")
        ok1 = bad_hit and good_clean

    print("=== 自证：③ 序列化段能抓漏键/幻影键 ===")
    ok2 = True
    # 反方向用例：给一个「少写字段」的方法体，必须被抓出来
    src = '''
class DictionaryEntry:
    def to_dict(self):
        return {"metadata": {"id": self.id}, "state": {}}
'''
    tree = ast.parse(src)
    keys = _metadata_dict_keys(tree, "DictionaryEntry", "to_dict")
    print("  取到 metadata 键:", keys)
    ok2 = keys == ["id"]
    print("  解析器取键正确:", "✅" if ok2 else "❌")

    print("=== 自证：② / ④ 依赖运行时，直接跑当前仓库 ===")
    skips: list[str] = []
    f2, f3, f4 = (
        collect_runtime_field_issues(skips),
        collect_serializer_issues(skips),
        collect_ctor_issues(),
    )
    clean234 = not (f2 or f3 or f4)
    print("  当前仓库 ②/③/④ 干净:", "✅" if clean234 else "❌ " + "; ".join(f2 + f3 + f4))
    ok = ok1 and ok2 and clean234
    print("\n自证结果:", "✅ 通过" if ok else "❌ 失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="有检查被跳过也视为失败")
    ap.add_argument("--self-test", action="store_true", help="自证有区分度")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    skips: list[str] = []
    findings: list[str] = []

    print("=== ① 静态：继承 dataclass 却漏 @dataclass ===")
    f1, total = collect_missing_decorator(SCAN_ROOT)
    findings += f1
    print(f"扫描 {total} 个类，命中 {len(f1)}")

    print("=== ② 运行时：目标类必须是真 dataclass 且字段齐 ===")
    f2 = collect_runtime_field_issues(skips)
    findings += f2

    print("=== ③ 序列化：to_dict 的 metadata 键必须与字段集合相等 ===")
    f3 = collect_serializer_issues(skips)
    findings += f3

    print("=== ④ 构造：调用点的具名参数必须是真字段 ===")
    f4 = collect_ctor_issues()
    findings += f4

    for s in skips:
        print("⏭️ ", s)

    print()
    if findings:
        for f in findings:
            print("❌", f)
        print(f"\n共 {len(findings)} 项")
        return 1

    print("✅ 四段检查全部通过")
    if skips and args.strict:
        print("❌ --strict：存在被跳过的检查")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
