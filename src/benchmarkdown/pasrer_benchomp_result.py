from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass()
class Device:
    brand: str
    device: str
    model: str
    sdk: int
    sdk_codename: str
    cpu_cores: int
    cpu_freq: int
    cpu_locked: bool
    mem_size_mb: int
    emulated: bool

    @staticmethod
    def default() -> Device:
        return Device(
            brand="NA",
            device="NA",
            model="NA",
            sdk=0,
            sdk_codename="",
            cpu_cores=0,
            cpu_freq=0,
            cpu_locked=True,
            mem_size_mb=0,
            emulated=True,
        )

    @property
    def id(self) -> str:
        return f"{self.device}"

    @property
    def label(self) -> str:
        # return f"{self.id} ({self.cpu_cores}-cores / {self.get_mem_formatted_str()})"
        return self.id

    def get_mem_formatted_str(self) -> str:
        # bigger than 1 GB
        if self.mem_size_mb >= 1000:
            return f"{self.mem_size_mb // 1000} GB"
        else:
            return f"{self.mem_size_mb} MB"

    def __eq__(self, other):
        if not isinstance(other, Device):
            return False

        return (
            self.brand == other.brand and
            self.device == other.device and
            self.model == other.model and
            self.sdk == other.sdk and
            self.sdk_codename == other.sdk_codename and
            self.cpu_cores == other.cpu_cores and
            self.cpu_freq == other.cpu_freq and
            self.cpu_locked == other.cpu_locked and
            self.mem_size_mb == other.mem_size_mb and
            self.emulated == other.emulated
        )


@dataclass
class CompareResult:
    id: str
    label: str
    statistic: float
    statistic_label: str
    verdict: str


@dataclass
class MeasureCompareResult:
    id: str
    label: str
    unit: str
    minimum: tuple[int, int]
    maximum: tuple[int, int]
    median: tuple[int, int]
    cv: tuple[int, int]
    runs: tuple[list[float], list[float]]
    results: dict[str, CompareResult]


@dataclass
class BenchmarkCompareResult:
    # device: Device
    name: str
    class_name: str
    total_runtime_ns: tuple[int, int]
    warmup_iterations: tuple[int, int]
    repeat_iterations: tuple[int, int]
    metrics: dict[str, MeasureCompareResult]
    thresholds: dict[str, float]

    @property
    def id(self) -> str:
        return f"{self.class_name}#{self.name}"


@dataclass
class AnalysisReport:
    format_version: int
    devices: list[Device]
    benchmarks: list[BenchmarkCompareResult]


def _json_read_device(data: dict[str, Any]) -> Device:
    version = data.get("version", {})
    return Device(
        brand=data.get("brand", ""),
        model=data.get("model", ""),
        device=data.get("device", ""),
        cpu_cores=data.get("cpuCoreCount", 0),
        cpu_freq=data.get("cpuMaxFreqHz", 0),
        cpu_locked=data.get("cpuLocked", True),
        mem_size_mb=data.get("memTotalBytes", 0) // (1000 * 1000),
        emulated=data.get("emulated", True),
        sdk=version.get("sdk", 0),
        sdk_codename=version.get("codename", ""),
    )


def _json_read_measure_comp_result(
    id: str, data: dict[str, Any]
) -> MeasureCompareResult:
    def _json_read_compare_result(id: str, data: dict[str, Any]) -> CompareResult:
        return CompareResult(
            id=id,
            label=data.get("label", ""),
            statistic=data.get("statistic", ""),
            statistic_label=data.get("statistic_label", ""),
            verdict=data.get("verdict", "unknown"),
        )

    results: dict[str, CompareResult] = {}
    for k, v in data.get("compareResults", {}).items():
        results[k] = _json_read_compare_result(k, v)

    return MeasureCompareResult(
        id=id,
        label=data.get("label", ""),
        unit=data.get("unit", ""),
        minimum=data.get("minimum", (0, 0)),
        maximum=data.get("maximum", (0, 0)),
        median=data.get("median", (0, 0)),
        cv=data.get("coefficientOfVariation", (0, 0)),
        runs=data.get("runs", [[], []]),
        results=results,
    )


def _json_read_bench_comp_result(data: dict[str, Any]) -> BenchmarkCompareResult:
    metrics: dict[str, MeasureCompareResult] = {}
    for k, v in data.get("metrics", {}).items():
        metrics[k] = _json_read_measure_comp_result(k, v)

    return BenchmarkCompareResult(
        name=data.get("name", ""),
        class_name=data.get("class", ""),
        total_runtime_ns=data.get("totalRunTimeNs", (0, 0)),
        warmup_iterations=data.get("warmupIterations", (0, 0)),
        repeat_iterations=data.get("repeatIterations", (0, 0)),
        metrics=metrics,
        thresholds=data.get("thresholds", {}),
    )


def json_read_analysis_report(data: dict[str, Any]) -> AnalysisReport:
    devices: list[Device] = []
    for d in data.get("devices", []):
        devices.append(_json_read_device(d))

    benchmarks: list[BenchmarkCompareResult] = []
    for b in data.get("benchmarks", []):
        benchmarks.append(_json_read_bench_comp_result(b))

    return AnalysisReport(
        format_version=data.get("formatVersion", 0),
        devices=devices,
        benchmarks=benchmarks,
    )

def json_load_analysis_report(path: Path | str) -> AnalysisReport | None:
    report: AnalysisReport | None = None

    with open(path, "r") as file:
        try:
            root = json.load(file)
            report = json_read_analysis_report(root)
        except JSONDecodeError | UnicodeDecodeError:
            logger.exception(f"failed to parse json file '{path}', invalid JSON document")
            return None

    return report
