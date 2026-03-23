"""数据质量门控 - 在数据流关键节点验证数据质量"""

import pandas as pd
import logging
from typing import List, Set, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger(__name__)


class QualityLevel(Enum):
    """数据质量等级"""
    PASS = "pass"           # 完全合格
    WARNING = "warning"      # 警告（部分问题）
    FAIL = "fail"           # 不合格


@dataclass
class QualityCheck:
    """质量检查项"""
    name: str
    passed: bool
    level: QualityLevel
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class QualityReport:
    """质量报告"""
    level: QualityLevel
    checks: List[QualityCheck] = field(default_factory=list)
    row_count: int = 0
    col_count: int = 0

    @property
    def passed(self) -> bool:
        return self.level != QualityLevel.FAIL

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.level == QualityLevel.WARNING)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if c.level == QualityLevel.FAIL)


class DataQualityGate:
    """
    数据质量门控

    在数据流的关键节点验证数据质量，发现问题及时报警

    用法:
        gate = DataQualityGate()

        # 检查数据
        report = gate.validate(market_data, context="realtime_tick")

        if not report.passed:
            logger.error(f"数据质量不合格: {report}")
        elif report.warning_count > 0:
            logger.warning(f"数据质量有警告: {report}")
    """

    REQUIRED_COLUMNS = ['code', 'p_change', 'volume']

    SECTOR_COLUMNS = ['sector', 'sector_id', 'industry', 'block']

    RECOMMENDED_COLUMNS = ['name', 'close', 'now', 'amount']

    def __init__(
        self,
        required_columns: Optional[List[str]] = None,
        strict_mode: bool = False
    ):
        self.required_columns = set(required_columns or self.REQUIRED_COLUMNS)
        self.sector_columns = set(self.SECTOR_COLUMNS)
        self.recommended_columns = set(self.RECOMMENDED_COLUMNS)
        self.strict_mode = strict_mode

        self._stats = {
            'total_checks': 0,
            'passed': 0,
            'warning': 0,
            'failed': 0,
        }

    def validate(
        self,
        data: pd.DataFrame,
        context: str = "unknown",
        min_rows: int = 1,
    ) -> QualityReport:
        """
        验证数据质量

        Args:
            data: 待验证的数据
            context: 数据来源上下文
            min_rows: 最小行数要求

        Returns:
            QualityReport: 质量报告
        """
        self._stats['total_checks'] += 1

        checks = []

        if data is None or not isinstance(data, pd.DataFrame):
            checks.append(QualityCheck(
                name="dataframe_type",
                passed=False,
                level=QualityLevel.FAIL,
                message=f"数据不是 DataFrame 类型: {type(data)}"
            ))
            return self._build_report(checks, 0, 0)

        data = self._ensure_p_change_column(data)

        row_count = len(data)
        col_count = len(data.columns)

        checks.extend([
            self._check_row_count(data, min_rows),
            self._check_required_columns(data),
            self._check_sector_columns(data),
            self._check_data_types(data),
            self._check_null_values(data),
            self._check_duplicate_codes(data),
        ])

        report = self._build_report(checks, row_count, col_count)

        self._update_stats(report)

        if report.level == QualityLevel.FAIL:
            logger.error(f"[{context}] 数据质量不合格: {report.failed_count} 项失败")
        elif report.level == QualityLevel.WARNING:
            logger.warning(f"[{context}] 数据质量有警告: {report.warning_count} 项")

        return report

    def _ensure_p_change_column(self, data: pd.DataFrame) -> pd.DataFrame:
        """如果 p_change 不存在但 close 和 now 存在，自动计算 p_change"""
        if 'p_change' in data.columns:
            return data

        if 'close' in data.columns and 'now' in data.columns:
            try:
                close = pd.to_numeric(data['close'], errors='coerce')
                now = pd.to_numeric(data['now'], errors='coerce')
                data = data.copy()
                data['p_change'] = ((now - close) / close * 100).fillna(0).replace([float('inf'), float('-inf')], 0)
                logger.debug(f"[DataQualityGate] 自动计算 p_change 列: (now - close) / close * 100")
            except Exception as e:
                logger.debug(f"[DataQualityGate] 计算 p_change 失败: {e}")

        return data

    def _check_row_count(self, data: pd.DataFrame, min_rows: int) -> QualityCheck:
        """检查行数"""
        row_count = len(data)
        passed = row_count >= min_rows
        return QualityCheck(
            name="row_count",
            passed=passed,
            level=QualityLevel.FAIL if not passed else QualityLevel.PASS,
            message=f"行数: {row_count} (要求 >= {min_rows})",
            details={'row_count': row_count, 'min_rows': min_rows}
        )

    def _check_required_columns(self, data: pd.DataFrame) -> QualityCheck:
        """检查必需列"""
        data_cols = set(data.columns)
        missing = self.required_columns - data_cols

        passed = len(missing) == 0
        level = QualityLevel.FAIL if not passed else QualityLevel.PASS

        if not passed:
            message = f"缺少必需列: {missing}"
        else:
            message = f"必需列完整: {self.required_columns & data_cols}"

        return QualityCheck(
            name="required_columns",
            passed=passed,
            level=level,
            message=message,
            details={'missing': list(missing), 'found': list(self.required_columns & data_cols)}
        )

    def _check_sector_columns(self, data: pd.DataFrame) -> QualityCheck:
        """检查板块相关列"""
        data_cols = set(data.columns)
        has_sector = bool(self.sector_columns & data_cols)

        if not has_sector:
            level = QualityLevel.WARNING
            message = "数据中没有板块列 (sector/sector_id/industry/block)"
        else:
            level = QualityLevel.PASS
            found = self.sector_columns & data_cols
            message = f"找到板块列: {found}"

        return QualityCheck(
            name="sector_columns",
            passed=True,
            level=level,
            message=message,
            details={'has_sector': has_sector}
        )

    def _check_data_types(self, data: pd.DataFrame) -> QualityCheck:
        """检查数据类型"""
        issues = []

        for col in self.required_columns:
            if col not in data.columns:
                continue

            dtype = data[col].dtype
            if pd.api.types.is_numeric_dtype(dtype):
                continue

            if col == 'code':
                if not pd.api.types.is_string_dtype(dtype) and not pd.api.types.is_object_dtype(dtype):
                    issues.append(f"{col}: {dtype}")
            elif col in ('p_change', 'volume', 'amount'):
                if not self._can_convert_to_numeric(data[col]):
                    issues.append(f"{col}: {dtype} (无法转换为数值)")

        passed = len(issues) == 0
        return QualityCheck(
            name="data_types",
            passed=passed,
            level=QualityLevel.FAIL if not passed else QualityLevel.PASS,
            message=f"数据类型检查: {'通过' if passed else f'问题列: {issues}'}",
            details={'issues': issues}
        )

    def _can_convert_to_numeric(self, series: pd.Series) -> bool:
        """检查 Series 是否可以转换为数值类型"""
        try:
            pd.to_numeric(series, errors='raise')
            return True
        except (TypeError, ValueError):
            numeric_count = pd.to_numeric(series, errors='coerce').notna().sum()
            total_count = len(series)
            return numeric_count >= total_count * 0.5

    def _check_null_values(self, data: pd.DataFrame) -> QualityCheck:
        """检查空值"""
        null_counts = data.isnull().sum()
        null_cols = null_counts[null_counts > 0]

        if len(null_cols) > 0:
            total_nulls = null_cols.sum()
            null_ratio = total_nulls / (len(data) * len(data.columns))
            level = QualityLevel.FAIL if null_ratio > 0.1 else QualityLevel.WARNING
            message = f"存在空值: {len(null_cols)} 列, 共 {total_nulls} 个"
        else:
            level = QualityLevel.PASS
            message = "无空值"

        return QualityCheck(
            name="null_values",
            passed=level != QualityLevel.FAIL,
            level=level,
            message=message,
            details={'null_cols': null_cols.to_dict() if len(null_cols) > 0 else {}}
        )

    def _check_duplicate_codes(self, data: pd.DataFrame) -> QualityCheck:
        """检查重复代码"""
        if 'code' not in data.columns:
            return QualityCheck(
                name="duplicate_codes",
                passed=True,
                level=QualityLevel.PASS,
                message="无 code 列，跳过重复检查"
            )

        duplicates = data['code'].duplicated().sum()
        passed = duplicates == 0
        level = QualityLevel.FAIL if not passed else QualityLevel.PASS

        return QualityCheck(
            name="duplicate_codes",
            passed=passed,
            level=level,
            message=f"重复代码: {duplicates} 个",
            details={'duplicate_count': duplicates}
        )

    def _build_report(
        self,
        checks: List[QualityCheck],
        row_count: int,
        col_count: int
    ) -> QualityReport:
        """构建报告"""
        failed = any(c.level == QualityLevel.FAIL for c in checks)
        warning = any(c.level == QualityLevel.WARNING for c in checks)

        if failed:
            level = QualityLevel.FAIL
        elif warning:
            level = QualityLevel.WARNING
        else:
            level = QualityLevel.PASS

        return QualityReport(
            level=level,
            checks=checks,
            row_count=row_count,
            col_count=col_count
        )

    def _update_stats(self, report: QualityReport):
        """更新统计"""
        if report.level == QualityLevel.FAIL:
            self._stats['failed'] += 1
        elif report.level == QualityLevel.WARNING:
            self._stats['warning'] += 1
        else:
            self._stats['passed'] += 1

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()

    def reset_stats(self):
        """重置统计"""
        self._stats = {
            'total_checks': 0,
            'passed': 0,
            'warning': 0,
            'failed': 0,
        }

    def __repr__(self) -> str:
        return f"DataQualityGate(required={self.required_columns}, strict={self.strict_mode})"


__all__ = ['DataQualityGate', 'QualityLevel', 'QualityCheck', 'QualityReport']
