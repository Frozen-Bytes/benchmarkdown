import logging
import math
import sys
from pathlib import Path
from typing import Any, cast

import pandas as pd

from benchmarkdown.markdown_writer import AlertType, MarkdownWriter
from benchmarkdown.parser_cli import parse_commandline_args
from benchmarkdown.pasrer_benchomp_result import (
    AnalysisReport,
    Device,
    json_load_analysis_report,
)

logger = logging.getLogger(__name__)

CATEGORY_MEASURES: dict[str, list[str]] = {
    "App Launch Time": [
        "TID",
        "TFD",
    ],
    "️Frame Rendering Time": [
        "FFD",
        "FFO",
    ],
    "Memory Usage": [
        "MEM_RSS_MAX",
        "MEM_RSS_ANON_MAX",
        "MEM_RSS_FILE_MAX",
        "MEM_HEAP_SIZE_MAX",
        "MEM_GPU_MAX",
        "MEM_RSS_LAST",
        "MEM_RSS_ANON_LAST",
        "MEM_RSS_FILE_LAST",
        "MEM_HEAP_SIZE_LAST",
        "MEM_GPU_LAST",
    ],
}

VERDICT_STR = {
    "UNKNOWN": "???",
    "IMPROVEMENT": "🟢 Improvement",
    "REGRESSION": "🔴 Regression",
    "NOT_SIGNIFICANT": "⚪ Insignificant ",
    "UNSTABLE": "🟡 UNSTABLE",
}


#############################################################################
# Helpers
#############################################################################

def _relative_diff(a: float, b: float) -> float:
    return (b - a) / a if not math.isclose(a, 0.0) else math.inf

def load_reports(files: list[Path]) -> list[AnalysisReport]:
    reports: list[AnalysisReport] = []
    for f in files:
        try:
            report: AnalysisReport | None = json_load_analysis_report(f)
            if report:
                reports.append(report)
            else:
                logger.error(f"invalid benchmark report '{f}', skipping.\n")
        except OSError:
            logger.exception(f"failed to open file {f} for reading.")
    return reports


def build_dataframe(reports: list[AnalysisReport]) -> tuple[pd.DataFrame, list[Device]]:
    def to_sec_from_ns(ns: float | int) -> float:
        return ns / 1_000_000_000.0

    devices: list[Device] = []
    device_name_count: dict[str, int] = {}

    rows: list[dict] = []
    for r in reports:
        if len(r.devices) != 1:
            logger.warning("multiple devices per analysis report not supported, skipping")
            continue

        device = r.devices[0]
        device_index = -1

        for index, d in enumerate(devices):
            if d == device:
                device_index = index

        if device_index == -1:
            device_index = len(devices)
            devices.append(device)

        device_name_count[device.device] = device_name_count.get(device.device, 0) + 1
        if device_name_count[device.device] > 1:
            device.device = f"{device.device}_{device_name_count[device.device] - 1:02d}"

        for bench in r.benchmarks:
            total_runtime_sec = (
                to_sec_from_ns(bench.total_runtime_ns[0]),
                to_sec_from_ns(bench.total_runtime_ns[1]),
            )

            base_row = {
                "device_index":       device_index,
                "benchmark_id":       bench.id,
                "benchmark_name":     bench.name,
                "benchmark_class":    bench.class_name,
                "total_runtime_sec":  total_runtime_sec,
                "repeat_iterations":  bench.repeat_iterations,
                "warmup_iterations":  bench.warmup_iterations,
            }

            for metric_id, measure in bench.metrics.items():
                for method_id, compare_result in measure.results.items():
                    rows.append({
                        **base_row,
                        "metric_id":            metric_id,
                        "metric_label":         measure.label,
                        "metric_unit":          measure.unit,
                        "metric_median":        measure.median,
                        "metric_runs":          measure.runs,
                        "compare_method_id":    method_id,
                        "compare_method_label": compare_result.label,
                        "verdict":              compare_result.verdict.upper(),
                        "statistic":            compare_result.statistic,
                        "statistic_label":      compare_result.statistic_label,
                        "threshold":            bench.thresholds.get(method_id, 0.0),
                    })

    df = pd.DataFrame(rows)
    return df, devices


#############################################################################

#############################################################################
# Markdown Building
#############################################################################

def _build_device_specs(md: MarkdownWriter, devices: list[Device]) -> None:
    md.begin_table(["Device", "Brand", "CPU", "Memory", "SDK"])
    for d in devices:
        md.table_row(
            [
                d.id,
                d.brand,
                f"{d.cpu_cores} @ {d.cpu_freq} Hz",
                d.get_mem_formatted_str(),
                f"{d.sdk} ({d.sdk_codename})",
            ]
        )
    md.end_table()


def _build_measure(
    md: MarkdownWriter,
    metric_df: pd.DataFrame,
    devices: list[Device],
    include_details_header=False,
) -> None:
    metric_id    = metric_df["metric_id"].iat[0]
    metric_label = metric_df["metric_label"].iat[0]
    metric_unit  = metric_df["metric_unit"].iat[0]

    if include_details_header:
        md.push_details(f"{metric_label} ({metric_id})")

    for _, method_df in metric_df.groupby("compare_method_id"):
        method_label = method_df["compare_method_label"].iat[0]
        thresholds = method_df["threshold"].tolist()
        has_multiple_threshold = len(set(thresholds)) > 1

        table_header: list[str] = [ ]

        table_header.append("Device")
        table_header.append("Median")
        table_header.append("Change (%)")
        table_header.append("Statistic")

        if has_multiple_threshold:
            table_header.append("Threshold")

        table_header.append("Status")

        if has_multiple_threshold:
            md.header(f"{method_label}", 4)
            table_header = [
                "Device",
                "Median",
                "Change (%)",
                "Statistic",
                "Threshold",
                "Status",
            ]
        else:
            md.header(f"{method_label} (threshold = {thresholds[0]:.3f})", 4)

        md.begin_table(table_header)
        for _, row in method_df.iterrows():
            device_index = cast(int, row["device_index"])
            device = devices[device_index] if row["device_index"] < len(devices) else Device.default()
            baseline_median, candidate_median = row["metric_median"]

            status = VERDICT_STR["UNKNOWN"]
            if row["verdict"] in VERDICT_STR:
                verdict = cast(str, row["verdict"])
                status = VERDICT_STR[verdict]

            table_row: list[Any] = []

            table_row.append(device.label)
            table_row.append(f"{int(baseline_median)} {metric_unit} vs {int(candidate_median)} {metric_unit}")
            table_row.append(f"{int(candidate_median - baseline_median)} ({_relative_diff(baseline_median, candidate_median):+.0%})")
            table_row.append(f"{row['statistic_label']}={row['statistic']:+.3f}")

            if has_multiple_threshold:
                table_row.append(row["threshold"])

            table_row.append(f"{status}")

            md.table_row(table_row)
        md.end_table()

    md.push_details("🗃️ Raw Runs")
    for _, row in metric_df.drop_duplicates("device_index").iterrows():
        device_index = cast(int, row["device_index"])
        device = devices[device_index] if row["device_index"] < len(devices) else Device.default()
        runs_a, runs_b = row["metric_runs"]
        min_len = min(len(runs_a), len(runs_b))
        max_len = max(len(runs_a), len(runs_b))

        md.push_details(f"📱 {device.label}")
        md.begin_table(["Run", "Baseline", "Candidate", "Change"])
        for i in range(max_len):
            a_val = f"{int(runs_a[i])} {metric_unit}" if i < len(runs_a) else "-"
            b_val = f"{int(runs_b[i])} {metric_unit}" if i < len(runs_b) else "-"
            change = f"{_relative_diff(runs_a[i], runs_b[i]):+.0%}" if i < min_len else "-"
            md.table_row([i, a_val, b_val, change])
        md.end_table()
        md.pop_details()
    md.pop_details()


    if include_details_header:
        md.pop_details()


def _build_benchmarks(md: MarkdownWriter, df: pd.DataFrame, devices: list[Device]) -> None:
    for _, bench_df in df.groupby("benchmark_id"):
        name = bench_df["benchmark_name"].iat[0]
        class_name = bench_df["benchmark_class"].iat[0]
        name_pascal = name[0].upper() + name[1:] if name else ""
        has_regression = (bench_df["verdict"] == "REGRESSION").any()

        md.push_details(f"{name_pascal}", open=has_regression)
        md.space()


        # Metadata
        md.text(f"Name: `{name}`")
        md.text(f"Class: `{class_name}`")
        md.text("")

        # Extra Metadata
        md.push_details("Extra Execution Metadata", bold=False, italic=True)
        md.begin_table(["Device", "Runtime (sec)", "Repeat Iterations", "Warmup Iterations"])
        for _, row in bench_df.drop_duplicates("device_index").iterrows():
            device_index = cast(int, row["device_index"])
            device = devices[device_index] if row["device_index"] < len(devices) else Device.default()
            rt = cast(tuple[int, int], row["total_runtime_sec"])
            rep = cast(tuple[int, int], row["repeat_iterations"])
            wrm = cast(tuple[int, int], row["warmup_iterations"])
            md.table_row(
                [
                    device.label,
                    f"{int(rt[0])} - {int(rt[1])}",
                    f"{rep[0]} - {rep[1]}",
                    f"{wrm[0]} - {wrm[1]}",
                ]
            )
        md.end_table()
        md.pop_details() # Extra Metadata

        for category, measures in CATEGORY_MEASURES.items():
            cat_df = cast(pd.DataFrame, bench_df[bench_df["metric_id"].isin(measures)])
            if cat_df.empty:
                continue

            md.push_details(category)
            unique_metrics = cast(pd.Series, cat_df["metric_id"]).unique()
            for metric_id in measures:
                metric_df = cast(pd.DataFrame, cat_df[cat_df["metric_id"] == metric_id])
                if metric_df.empty:
                    continue

                _build_measure(
                    md,
                    metric_df,
                    devices,
                    include_details_header=(len(unique_metrics) > 1),
                )
            md.pop_details()


        md.pop_details() # Benchmark Name


def build_markdown_report(df: pd.DataFrame, devices: list[Device]) -> str:
    md = MarkdownWriter()
    md.header("📊 Android Performance Analysis Report", 1)

    regression_count = df[df["verdict"] == "REGRESSION"].groupby("benchmark_id").ngroups
    if regression_count > 0:
        md.alert_block(
            f"Detected regression for {regression_count} Macrobenchmark(s). Further investigation is required.",
            AlertType.WARNING,
        )

    # Summary Table
    md.header("🚀 Summary", 2)
    md.begin_table(["MacroBenchmark", "Metric", "Status"])
    mixed_count = 0
    for _, bench_df in df.groupby("benchmark_id"):
        name_pascal = bench_df["benchmark_name"].iat[0]
        name_pascal = name_pascal[0].upper() + name_pascal[1:] if name_pascal else ""

        for category, measures in CATEGORY_MEASURES.items():
            cat_df = bench_df[bench_df["metric_id"].isin(measures)]
            if cat_df.empty:
                continue

            has_regression = (cat_df["verdict"] == "REGRESSION").any()
            has_improvement = (cat_df["verdict"] == "IMPROVEMENT").any()

            status = "Unknown"
            if has_regression and has_improvement:
                mixed_count += 1
                status = "UNSTABLE"
            elif has_regression:
                status = "REGRESSED"
            elif has_improvement:
                status = "IMPROVED"
            else:
                status = "NOT_SIGNIFICANT"

            md.table_row([name_pascal, category, VERDICT_STR[status]])
    md.end_table()

    if mixed_count > 0:
        md.alert_block(
            f"Detected both regression, and improvement for {mixed_count} MacroBenchmark(s). Further investigation is required.",
            AlertType.CAUTION,
        )

    md.header("⌛ Benchmarks", 2)
    _build_benchmarks(md, df, devices)

    md.header("📱 Device Specifications", 2)
    _build_device_specs(md, devices)

    return md.to_string()

#############################################################################

def main() -> int:
    conf = parse_commandline_args()

    reports = load_reports(conf.inputs)
    df, devices = build_dataframe(reports)
    md = build_markdown_report(df, devices)

    if conf.output_path:
        with open(conf.output_path, "w") as f:
            f.write(md)
    else:
        print(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
