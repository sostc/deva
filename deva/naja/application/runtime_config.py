from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class LabModeConfig:
    enabled: bool = False
    table_name: Optional[str] = None
    interval: float = 1.0
    speed: float = 1.0
    debug: bool = False

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "LabModeConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            table_name=data.get("table_name"),
            interval=float(data.get("interval", 1.0)),
            speed=float(data.get("speed", 1.0)),
            debug=bool(data.get("debug", False)),
        )

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "table_name": self.table_name,
            "interval": self.interval,
            "speed": self.speed,
            "debug": self.debug,
        }


@dataclass(frozen=True)
class NewsRadarModeConfig:
    enabled: bool = False
    mode: str = "normal"
    speed: float = 1.0
    interval: float = 0.5

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "NewsRadarModeConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            mode=str(data.get("mode", "normal") or "normal"),
            speed=float(data.get("speed", 1.0)),
            interval=float(data.get("interval", 0.5)),
        )

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "speed": self.speed,
            "interval": self.interval,
        }


@dataclass(frozen=True)
class CognitionDebugConfig:
    enabled: bool = False

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "CognitionDebugConfig":
        data = data or {}
        return cls(enabled=bool(data.get("enabled", False)))

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled}


@dataclass(frozen=True)
class TuneModeConfig:
    enabled: bool = False
    search_method: str = "grid"
    max_samples: int = 100
    export_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "TuneModeConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            search_method=str(data.get("search_method", "grid") or "grid"),
            max_samples=int(data.get("max_samples", 100)),
            export_path=data.get("export_path"),
        )

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "search_method": self.search_method,
            "max_samples": self.max_samples,
            "export_path": self.export_path,
        }


@dataclass(frozen=True)
class WebServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass(frozen=True)
class AppRuntimeConfig:
    server: WebServerConfig = WebServerConfig()
    lab: LabModeConfig = LabModeConfig()
    news_radar: NewsRadarModeConfig = NewsRadarModeConfig()
    cognition_debug: CognitionDebugConfig = CognitionDebugConfig()
    tune: TuneModeConfig = TuneModeConfig()

    @classmethod
    def from_legacy(
        cls,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        lab_config: Optional[dict[str, Any]] = None,
        news_radar_config: Optional[dict[str, Any]] = None,
        cognition_debug_config: Optional[dict[str, Any]] = None,
        tune_config: Optional[dict[str, Any]] = None,
    ) -> "AppRuntimeConfig":
        return cls(
            server=WebServerConfig(host=host, port=port),
            lab=LabModeConfig.from_dict(lab_config),
            news_radar=NewsRadarModeConfig.from_dict(news_radar_config),
            cognition_debug=CognitionDebugConfig.from_dict(cognition_debug_config),
            tune=TuneModeConfig.from_dict(tune_config),
        )
