"""
Benchmark heartbeat latency with concurrent writes.
Tests concurrent JSONL writes to employees.jsonl.
Target: < 50ms p95 latency.

Usage:
    python tests/benchmark_heartbeat_latency.py
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple


def setup_employees_file():
    """Ensure employees.jsonl exists for testing."""
    employees_path = Path("employees.jsonl")
    if not employees_path.exists():
        employees_path.touch()
    return employees_path


def write_heartbeat(emp_id: str, sequence: int, employees_path: Path) -> Tuple[int, float, bool]:
    """
    Write a single heartbeat record to the employees file.
    
    Returns:
        Tuple of (sequence, latency_ms, success)
    """
    start = time.perf_counter()
    
    record = {
        "agent_id": emp_id,
        "role": "Benchmark Agent",
        "status": "active",
        "sequence": sequence,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%f"),
        "heartbeat_latency_ms": 0.0  # Calculated separately
    }
    
    try:
        with open(employees_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        return (sequence, elapsed_ms, True)
    except Exception as e:
        return (sequence, 0, False)


def run_benchmark(
    num_threads: int = 10,
    iterations_per_thread: int = 100,
    target_file: str = "employees.jsonl"
) -> dict:
    """
    Run concurrent write benchmark.
    
    Args:
        num_threads: Number of concurrent threads
        iterations_per_thread: Writes per thread
        target_file: Path to JSONL file
    
    Returns:
        Benchmark results dictionary
    """
    employees_path = setup_employees_file()
    
    # Clear previous test data
    if employees_path.exists():
        employees_path.unlink()
        employees_path.touch()
    
    results: List[Tuple[int, float]] = []
    errors = 0
    
    def worker(thread_id: int):
        nonlocal errors
        for seq in range(iterations_per_thread):
            emp_id = f"benchmark-{thread_id}-{seq}"
            seq_num = thread_id * iterations_per_thread + seq
            _, latency, success = write_heartbeat(emp_id, seq_num, employees_path)
            
            if success:
                results.append((seq_num, latency))
            else:
                errors += 1
    
    # Run benchmark
    start_total = time.perf_counter()
    
    threads = []
    for thread_id in range(num_threads):
        t = threading.Thread(target=worker, args=(thread_id,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    total_duration = time.perf_counter() - start_total
    
    # Calculate statistics
    latencies = [r[1] for r in results if r[1] > 0]
    
    if not latencies:
        return {"error": "No successful writes"}
    
    latencies.sort()
    
    # Basic stats
    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)
    
    # Percentiles
    def percentile(data: List[float], p: float) -> float:
        k = (len(data) - 1) * p / 100
        f = int(k)
        c = f + 1
        if c >= len(data):
            return data[f]
        return data[f] + (data[c] - data[f]) * (k - f)
    
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    
    # Throughput
    total_writes = len(results)
    throughput = total_writes / total_duration
    
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {
            "num_threads": num_threads,
            "iterations_per_thread": iterations_per_thread,
            "total_writes": total_writes,
        },
        "duration_seconds": round(total_duration, 3),
        "throughput_ops": round(throughput, 2),
        "latency_ms": {
            "avg": round(avg_latency, 3),
            "min": round(min_latency, 3),
            "max": round(max_latency, 3),
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "p99": round(p99, 3),
        },
        "target_p95_ms": 50,
        "passed": p95 < 50,
        "errors": errors,
    }


def main():
    """Run benchmark and print results."""
    print("=" * 60)
    print("Benchmark: Heartbeat Latency (Concurrency Test)")
    print("=" * 60)
    print()
    
    # Run with different thread counts
    for threads in [1, 5, 10, 20]:
        print(f"\nConfig: {threads} threads, 100 writes each ({threads * 100} total)")
        print("-" * 60)
        
        result = run_benchmark(
            num_threads=threads,
            iterations_per_thread=100,
            target_file="employees.jsonl"
        )
        
        print(f"Duration:    {result['duration_seconds']}s")
        print(f"Throughput:  {result['throughput_ops']:.1f} ops/s")
        print(f"Errors:      {result['errors']}")
        print()
        print("Latency Statistics:")
        print(f"  Average:   {result['latency_ms']['avg']:.3f} ms")
        print(f"  Min:       {result['latency_ms']['min']:.3f} ms")
        print(f"  Max:       {result['latency_ms']['max']:.3f} ms")
        print(f"  P50:       {result['latency_ms']['p50']:.3f} ms")
        print(f"  P95:       {result['latency_ms']['p95']:.3f} ms")
        print(f"  P99:       {result['latency_ms']['p99']:.3f} ms")
        print(f"  Target:    {result['target_p95_ms']} ms")
        print(f"  PASSED:    {result['passed']} ✓" if result['passed'] else f"  PASSED:    {result['passed']} ✗")
        print()
    
    print("=" * 60)
    print("Benchmark Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
