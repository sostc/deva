"""守卫：数据源 ``enabled: false`` 必须真的停用，而不是只在界面上灰一下。

背景（2026-10-21 实查）：`下载目录监控`（id=02bf46dfb976）从 2026-04 起就没用了 ——
它每 2 秒扫一次 ``~/Downloads``，产出的 10 条事件没人消费，还顺手把**每个下载
文件名** ``print`` 进日志（Broken pipe 的来源）。决定停用，结果发现：

    YAML 里写 ``metadata.enabled: false`` → NB 里读回来是 ``None``
    → 重启后它照样 running

根因有三层，缺一层都白改：

1. ``DataSourceMetadata`` 里**根本没有 enabled 字段**（只有 UI 的文件侧有），
   于是文件里的 false 在建 DataSourceEntry 时被静默丢弃；
2. ``_create_entry_from_file_config()`` 不传 enabled，就算有字段也会是默认 True；
3. ``restore_running_states()`` 只问 ``was_running``，从来不看 enabled。

最毒的是第三层：界面上显示「已停用」，实际每次重启都被拉起来跑，
台账和配置说的是两件事。本守卫钉的是**动作**（start 有没有被调用），
不是「代码里有没有那行判断」—— 后者能被任一层的遗漏骗过去。
"""

from __future__ import annotations

import argparse
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ❗必须早于任何 deva 导入：把 NB 落盘位置重定向到临时 sqlite，
# 免得守卫跑一遍把生产库写脏（verify_guard_db_isolation 会查这一条）。
from guard_sandbox import isolate_guard_db  # noqa: E402

isolate_guard_db()

from deva.naja.datasource.manager import DataSourceManager  # noqa: E402
from deva.naja.datasource.models import DataSourceMetadata, DataSourceState  # noqa: E402

# ❗旧实现（负向注入用）：恢复时只看 was_running，不看 enabled。
# 守卫必须能在它上面报错，否则说明守卫根本没在守「停用」这件事。
OLD_RESTORE_SRC = '''
def _old_restore_running_states(self):
    restored = failed = skipped = 0
    results = []
    with self._items_lock:
        entries = list(self._items.values())
    for entry in entries:
        try:
            prep = entry.prepare_for_recovery()
            if not prep.get("can_recover"):
                skipped += 1
                results.append({"entry_id": entry.id, "entry_name": entry.name,
                                "success": False, "reason": prep.get("reason")})
                continue
            r = entry.start()
            if r.get("success"):
                restored += 1
                results.append({"entry_id": entry.id, "entry_name": entry.name, "success": True})
            else:
                failed += 1
                results.append({"entry_id": entry.id, "entry_name": entry.name,
                                "success": False, "error": r.get("error")})
        except Exception as e:
            failed += 1
            results.append({"entry_id": getattr(entry, "id", "?"), "entry_name": "",
                            "success": False, "error": str(e)})
    return {"success": True, "restored_count": restored, "failed_count": failed,
            "skipped_count": skipped, "results": results}
'''


class _FakeEntry:
    """只提供 restore_running_states 真正会用到的接口"""

    def __init__(self, entry_id: str, name: str, enabled: bool, status: str = "running"):
        self.id = entry_id
        self.name = name
        self._metadata = DataSourceMetadata(id=entry_id, name=name, enabled=enabled)
        self._state = DataSourceState(status=status)
        self.start_calls = 0
        self.save_calls = 0

    def prepare_for_recovery(self) -> dict:
        return {"can_recover": True, "func": lambda: None, "reason": "was_running_flag"}

    def start(self) -> dict:
        self.start_calls += 1
        return {"success": True}

    def save(self) -> None:
        self.save_calls += 1

    @property
    def was_running(self) -> bool:
        return True

    @property
    def is_running(self) -> bool:
        return False


class _FakeManager:
    """绕过单例/容器，直接提供 restore_running_states 需要的字段"""

    def __init__(self, entries: list):
        self._items = {e.id: e for e in entries}
        self._items_lock = threading.Lock()

    def _log(self, *args, **kwargs) -> None:
        pass


def _restore(restore_fn, entries: list) -> dict:
    return restore_fn(_FakeManager(entries))


def _check_disabled_not_started(restore_fn) -> tuple:
    """① 停用条目就算 was_running=True 也不许被拉起"""
    e = _FakeEntry("ds_disabled", "下载目录监控", enabled=False)
    res = _restore(restore_fn, [e])
    reasons = [r.get("reason") for r in res.get("results", [])]
    ok = (
        e.start_calls == 0
        and res.get("restored_count") == 0
        and res.get("skipped_count") == 1
        and "disabled_by_config" in reasons
    )
    detail = (
        f"start={e.start_calls} restored={res.get('restored_count')} "
        f"skipped={res.get('skipped_count')} reasons={reasons}"
    )
    return ok, detail


def _check_enabled_still_restored(restore_fn) -> tuple:
    """② 启用条目必须照常恢复（防止改宽把正常恢复一起卡住）"""
    e = _FakeEntry("ds_enabled", "金十财经快讯", enabled=True)
    res = _restore(restore_fn, [e])
    ok = e.start_calls == 1 and res.get("restored_count") == 1
    return ok, f"start={e.start_calls} restored={res.get('restored_count')}"


def _check_disabled_clears_stale_running(restore_fn) -> tuple:
    """③ 停用条目必须回写：遗留 running 要抹成 stopped，已经是 stopped 也要落盘

    ❗后半句是实查补上的：修好第一次后 NB 里 ``metadata.enabled`` 仍是 ``None``，
    因为它当时已是 stopped，早年那版只在「状态有变化」时才 save。
    台账上就成了「配置说停用、库里没有这个字段」—— 又一次两边对不上。
    """
    stale = _FakeEntry("ds_stale", "下载目录监控", enabled=False, status="running")
    already = _FakeEntry("ds_already", "下载目录监控2", enabled=False, status="stopped")
    _restore(restore_fn, [stale, already])
    ok = (
        stale._state.status == "stopped"
        and stale.save_calls >= 1
        and already.save_calls >= 1
    )
    return ok, (
        f"stale: status={stale._state.status} save={stale.save_calls} | "
        f"already_stopped: save={already.save_calls}"
    )


def _check_default_enabled() -> tuple:
    """④ 默认必须是启用：历史条目没有这个字段，不能因为加字段被集体停用"""
    ok = DataSourceMetadata(id="x", name="x").enabled is True
    return ok, f"default enabled={DataSourceMetadata(id='x', name='x').enabled}"


def _check_round_trip() -> tuple:
    """⑤ 存取一轮不许把 false 变回 true（否则重启又活了）"""
    from deva.naja.datasource.entry import DataSourceEntry

    entry = DataSourceEntry(
        metadata=DataSourceMetadata(id="ds_rt", name="rt", enabled=False),
        state=DataSourceState(),
    )
    back = DataSourceEntry.from_dict(entry.to_dict())
    ok = back._metadata.enabled is False
    return ok, f"round-trip enabled={back._metadata.enabled}"


def _check_file_config_passthrough(restore_fn) -> tuple:
    """⑥ YAML 的 enabled=false 要一路走到「恢复时不启动」（端到端链）"""
    from deva.naja.config.file_config import ConfigFileItem, DatasourceConfigMetadata

    item = ConfigFileItem(
        name="下载目录监控",
        config_type="datasources",
        metadata=DatasourceConfigMetadata(
            id="ds_file", name="下载目录监控", enabled=False, source_type="directory"
        ),
        parameters={"enabled": False, "interval_seconds": 5},
        config={"source_type": "directory"},
        func_code="def fetch_data(event):\n    return {}\n",
    )
    entry = DataSourceManager._create_entry_from_file_config(_FakeManager([]), item)
    if entry is None:
        return False, "文件配置没造出条目"
    # 恢复流程要拿到 was_running=True 才会尝试启动，这里手动置上，
    # 确保「没被启动」是因为 enabled，而不是因为 was_running 本就是 False。
    entry._was_running = True
    # ❗数「有没有调用 start」，而不是看 start 的返回值：
    # 真实的 directory 类型 start() 自己就可能失败（返回 success=False），
    # 那样「停用」和「启动失败」在结果上都是 restored=0，旧实现会被漏过。
    calls = {"n": 0}

    def _counting_start() -> dict:
        calls["n"] += 1
        return {"success": True}

    entry.start = _counting_start
    _restore(restore_fn, [entry])
    ok = getattr(entry._metadata, "enabled", None) is False and calls["n"] == 0
    return ok, f"metadata.enabled={getattr(entry._metadata, 'enabled', None)} start_calls={calls['n']}"


def _all_checks() -> list:
    restore_fn = DataSourceManager.restore_running_states
    fails: list = []
    for label, fn in (
        ("停用条目不被拉起", lambda: _check_disabled_not_started(restore_fn)),
        ("启用条目照常恢复", lambda: _check_enabled_still_restored(restore_fn)),
        ("停用条目抹掉遗留 running", lambda: _check_disabled_clears_stale_running(restore_fn)),
        ("默认启用", _check_default_enabled),
        ("存取往返保留 false", _check_round_trip),
        ("YAML enabled=false 端到端不启动", lambda: _check_file_config_passthrough(restore_fn)),
    ):
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        print(f"  {'✅' if ok else '❌'} {label}  （{detail}）")
        if not ok:
            fails.append(label)
    return fails


def _injections() -> list:
    mod = types.ModuleType("_old_restore")
    exec(OLD_RESTORE_SRC, mod.__dict__)
    old = mod._old_restore_running_states

    results = []
    for label, fn in (
        ("停用条目不被拉起", lambda: _check_disabled_not_started(old)),
        ("停用条目抹掉遗留 running", lambda: _check_disabled_clears_stale_running(old)),
        ("YAML enabled=false 端到端不启动", lambda: _check_file_config_passthrough(old)),
    ):
        try:
            ok, _detail = fn()
            results.append((label, not ok))
        except Exception:
            results.append((label, True))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exercise-injections", action="store_true")
    args = ap.parse_args()

    if args.exercise_injections:
        print("=== 负向注入（旧实现必须被抓到）===")
        results = _injections()
        hit = 0
        for label, caught in results:
            print(f"  {'✅ 抓到' if caught else '❌ 漏了'}  {label}")
            if caught:
                hit += 1
        print(f"注入检出 {hit}/{len(results)}")
        return 0 if hit == len(results) else 1

    print("=== 数据源 enabled=false 是否真的停用 ===")
    fails = _all_checks()
    if fails:
        print("❌ 守卫失败：" + "、".join(fails))
        return 1
    print("✅ enabled=false 会阻止恢复启动，启用条目不受影响")
    return 0


if __name__ == "__main__":
    sys.exit(main())
