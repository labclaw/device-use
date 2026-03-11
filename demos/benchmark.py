#!/usr/bin/env python3
"""Benchmark — measure device-use middleware performance.

Measures:
  - Orchestrator startup time
  - Tool routing latency
  - Pipeline execution (sequential vs parallel)
  - NMR processing throughput
  - Event system overhead

Usage:
    python demos/benchmark.py
"""

import logging
import statistics
import time
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from device_use import create_orchestrator
from device_use.orchestrator import Pipeline, PipelineStep


def _timer(fn, n=10):
    """Run fn n times and return (mean_ms, std_ms, min_ms)."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return (
        statistics.mean(times),
        statistics.stdev(times) if len(times) > 1 else 0,
        min(times),
    )


def bench_startup():
    """Measure orchestrator startup time."""
    mean, std, best = _timer(create_orchestrator, n=5)
    return {"name": "Orchestrator startup", "mean_ms": mean, "std_ms": std, "best_ms": best}


def bench_tool_routing():
    """Measure tool routing latency (call_tool overhead)."""
    orch = create_orchestrator()

    def call():
        orch.call_tool("topspin.list_datasets")

    mean, std, best = _timer(call, n=50)
    return {"name": "Tool routing (list_datasets)", "mean_ms": mean, "std_ms": std, "best_ms": best}


def bench_nmr_process():
    """Measure NMR processing throughput."""
    orch = create_orchestrator()
    datasets = orch.call_tool("topspin.list_datasets")
    path = datasets[0]["path"]

    def process():
        orch.call_tool("topspin.process", data_path=path)

    mean, std, best = _timer(process, n=5)
    return {"name": "NMR process (FT+phase+peaks)", "mean_ms": mean, "std_ms": std, "best_ms": best}


def bench_pipeline_sequential():
    """Measure sequential pipeline execution."""
    orch = create_orchestrator()
    datasets = orch.call_tool("topspin.list_datasets")

    pipeline = Pipeline("bench_seq")
    for i, ds in enumerate(datasets[:4]):
        pipeline.add_step(PipelineStep(
            name=f"process_{i}",
            tool_name="topspin.process",
            params={"data_path": ds["path"]},
        ))

    def run():
        orch.run(pipeline)

    mean, std, best = _timer(run, n=3)
    return {"name": f"Sequential pipeline ({len(pipeline)} steps)", "mean_ms": mean, "std_ms": std, "best_ms": best}


def bench_pipeline_parallel():
    """Measure parallel vs sequential I/O-bound steps."""
    import time as _time
    orch = create_orchestrator()

    # Simulate I/O-bound steps (network calls, instrument waits)
    def io_step(ctx, delay=0.05):
        _time.sleep(delay)
        return "done"

    n_steps = 8

    # Sequential
    seq_pipeline = Pipeline("bench_seq_io")
    for i in range(n_steps):
        seq_pipeline.add_step(PipelineStep(
            name=f"io_{i}", handler=io_step,
        ))

    t0 = time.perf_counter()
    orch.run(seq_pipeline)
    seq_ms = (time.perf_counter() - t0) * 1000

    # Parallel
    par_pipeline = Pipeline("bench_par_io")
    for i in range(n_steps):
        par_pipeline.add_step(PipelineStep(
            name=f"io_{i}", handler=io_step, parallel="batch",
        ))

    t0 = time.perf_counter()
    orch.run(par_pipeline)
    par_ms = (time.perf_counter() - t0) * 1000

    speedup = seq_ms / par_ms if par_ms > 0 else 0
    return {
        "name": f"Parallel speedup ({n_steps} I/O steps)",
        "mean_ms": par_ms,
        "std_ms": 0,
        "best_ms": par_ms,
        "extra": f"seq={seq_ms:.0f}ms par={par_ms:.0f}ms → {speedup:.1f}x",
    }


def bench_events():
    """Measure event system overhead."""
    orch = create_orchestrator()
    event_count = [0]
    orch.on_event(lambda e: event_count.__setitem__(0, event_count[0] + 1))

    pipeline = Pipeline("bench_events")
    for i in range(10):
        pipeline.add_step(PipelineStep(
            name=f"step_{i}",
            handler=lambda ctx: None,
        ))

    def run():
        event_count[0] = 0
        orch.run(pipeline)

    mean, std, best = _timer(run, n=10)
    return {
        "name": f"10-step pipeline with events ({event_count[0]} events)",
        "mean_ms": mean, "std_ms": std, "best_ms": best,
    }


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║              device-use — Performance Benchmark              ║
╚══════════════════════════════════════════════════════════════╝
""")

    benchmarks = [
        bench_startup,
        bench_tool_routing,
        bench_nmr_process,
        bench_pipeline_sequential,
        bench_pipeline_parallel,
        bench_events,
    ]

    results = []
    for bench_fn in benchmarks:
        print(f"  Running: {bench_fn.__doc__.strip()}...", end="", flush=True)
        result = bench_fn()
        results.append(result)
        print(f" {result['mean_ms']:.1f}ms")

    print(f"\n  {'Benchmark':<45} {'Mean':>8} {'Std':>8} {'Best':>8}")
    print(f"  {'-'*69}")
    for r in results:
        line = f"  {r['name']:<45} {r['mean_ms']:>7.1f}ms {r['std_ms']:>7.1f}ms {r['best_ms']:>7.1f}ms"
        if "extra" in r:
            line += f"  ({r['extra']})"
        print(line)

    print(f"\n  Total benchmarks: {len(results)}")
    print()


if __name__ == "__main__":
    main()
