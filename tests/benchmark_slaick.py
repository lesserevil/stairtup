"""
Benchmark tests for Slaick messaging system.

Measures:
- Message throughput (messages/second)
- Concurrent write performance
- Latency under load
- File I/O performance with multiple writers
"""

import asyncio
import json
import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import List, Tuple
import statistics

from app.company.slaick import Slaick


def worker_process(temp_path: str, worker_id: int, num_messages: int) -> int:
    """Worker function for process pool - must be at module level for pickling."""
    slaick = Slaick(Path(temp_path))
    for i in range(num_messages):
        msg_id = worker_id * num_messages + i
        slaick.append_message(
            from_agent=f"proc-{worker_id}",
            to_agent=f"proc-{(worker_id + 1) % 10}",
            msg_type="PROGRESS",
            payload={"worker_id": worker_id, "message_id": msg_id}
        )
    return num_messages


def benchmark_sequential_writes(num_messages: int = 1000) -> dict:
    """Benchmark sequential message writes."""
    with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        slaick = Slaick(temp_path)
        
        start_time = time.time()
        for i in range(num_messages):
            slaick.append_message(
                from_agent=f"agent-{i % 10}",
                to_agent=f"agent-{(i + 1) % 10}",
                msg_type="PROGRESS",
                payload={"message": f"Test message {i}", "iteration": i}
            )
        end_time = time.time()
        
        duration = end_time - start_time
        throughput = num_messages / duration
        
        return {
            "test": "sequential_writes",
            "num_messages": num_messages,
            "duration_seconds": round(duration, 3),
            "throughput_messages_per_sec": round(throughput, 2),
            "avg_latency_ms": round((duration / num_messages) * 1000, 3),
        }
    finally:
        temp_path.unlink(missing_ok=True)


def benchmark_concurrent_writes(num_messages: int = 1000, num_workers: int = 10) -> dict:
    """Benchmark concurrent message writes using threads."""
    with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        messages_per_worker = num_messages // num_workers
        
        def worker(worker_id: int) -> int:
            """Worker that writes messages to the shared file."""
            slaick = Slaick(temp_path)
            for i in range(messages_per_worker):
                msg_id = worker_id * messages_per_worker + i
                slaick.append_message(
                    from_agent=f"worker-{worker_id}",
                    to_agent=f"worker-{(worker_id + 1) % num_workers}",
                    msg_type="PROGRESS",
                    payload={"worker_id": worker_id, "message_id": msg_id}
                )
            return messages_per_worker
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker, i) for i in range(num_workers)]
            results = [f.result() for f in futures]
        
        end_time = time.time()
        
        duration = end_time - start_time
        total_messages = sum(results)
        throughput = total_messages / duration
        
        return {
            "test": "concurrent_writes_threads",
            "num_messages": total_messages,
            "num_workers": num_workers,
            "duration_seconds": round(duration, 3),
            "throughput_messages_per_sec": round(throughput, 2),
            "avg_latency_ms": round((duration / total_messages) * 1000, 3),
        }
    finally:
        temp_path.unlink(missing_ok=True)


def benchmark_concurrent_writes_processes(num_messages: int = 1000, num_workers: int = 4) -> dict:
    """Benchmark concurrent message writes using processes."""
    with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        messages_per_worker = num_messages // num_workers
        
        start_time = time.time()
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_process, str(temp_path), i, messages_per_worker) 
                      for i in range(num_workers)]
            results = [f.result() for f in futures]
        
        end_time = time.time()
        
        duration = end_time - start_time
        total_messages = sum(results)
        throughput = total_messages / duration
        
        return {
            "test": "concurrent_writes_processes",
            "num_messages": total_messages,
            "num_workers": num_workers,
            "duration_seconds": round(duration, 3),
            "throughput_messages_per_sec": round(throughput, 2),
            "avg_latency_ms": round((duration / total_messages) * 1000, 3),
        }
    finally:
        temp_path.unlink(missing_ok=True)


def benchmark_read_performance(num_messages: int = 1000) -> dict:
    """Benchmark message read performance."""
    with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        # Write messages first
        slaick = Slaick(temp_path)
        for i in range(num_messages):
            slaick.append_message(
                from_agent=f"agent-{i % 10}",
                to_agent=f"agent-{(i + 1) % 10}",
                msg_type="PROGRESS",
                payload={"message": f"Test message {i}"}
            )
        
        # Benchmark reads
        start_time = time.time()
        
        # Read all messages multiple times
        for _ in range(10):
            messages = slaick._read_all_messages()
            assert len(messages) == num_messages
        
        end_time = time.time()
        
        duration = end_time - start_time
        iterations = 10
        avg_read_time = duration / iterations
        
        return {
            "test": "read_performance",
            "num_messages": num_messages,
            "iterations": iterations,
            "total_duration_seconds": round(duration, 3),
            "avg_read_time_seconds": round(avg_read_time, 6),
            "messages_per_second": round(num_messages / avg_read_time, 2),
        }
    finally:
        temp_path.unlink(missing_ok=True)


def benchmark_latency(num_samples: int = 100) -> dict:
    """Benchmark write latency distribution."""
    with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        slaick = Slaick(temp_path)
        latencies = []
        
        for i in range(num_samples):
            start = time.perf_counter()
            slaick.append_message(
                from_agent="latency-test",
                to_agent="latency-test",
                msg_type="PROGRESS",
                payload={"iteration": i}
            )
            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # Convert to ms
        
        return {
            "test": "latency_distribution",
            "num_samples": num_samples,
            "min_ms": round(min(latencies), 3),
            "max_ms": round(max(latencies), 3),
            "mean_ms": round(statistics.mean(latencies), 3),
            "median_ms": round(statistics.median(latencies), 3),
            "stdev_ms": round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0,
            "p95_ms": round(sorted(latencies)[int(num_samples * 0.95)], 3),
            "p99_ms": round(sorted(latencies)[int(num_samples * 0.99)], 3),
        }
    finally:
        temp_path.unlink(missing_ok=True)


def run_all_benchmarks() -> dict:
    """Run all benchmarks and return results."""
    print("Running Slaick Messaging Benchmarks")
    print("=" * 50)
    
    results = {}
    
    # Sequential writes
    print("\n1. Sequential Writes (1000 messages)...")
    results["sequential"] = benchmark_sequential_writes(1000)
    print(f"   Throughput: {results['sequential']['throughput_messages_per_sec']} msg/s")
    
    # Concurrent writes (threads)
    print("\n2. Concurrent Writes - Threads (1000 messages, 10 workers)...")
    results["concurrent_threads"] = benchmark_concurrent_writes(1000, 10)
    print(f"   Throughput: {results['concurrent_threads']['throughput_messages_per_sec']} msg/s")
    
    # Concurrent writes (processes)
    print("\n3. Concurrent Writes - Processes (1000 messages, 4 workers)...")
    results["concurrent_processes"] = benchmark_concurrent_writes_processes(1000, 4)
    print(f"   Throughput: {results['concurrent_processes']['throughput_messages_per_sec']} msg/s")
    
    # Read performance
    print("\n4. Read Performance (1000 messages, 10 iterations)...")
    results["read"] = benchmark_read_performance(1000)
    print(f"   Avg read time: {results['read']['avg_read_time_seconds']:.6f}s")
    
    # Latency distribution
    print("\n5. Latency Distribution (100 samples)...")
    results["latency"] = benchmark_latency(100)
    print(f"   Mean: {results['latency']['mean_ms']:.3f}ms, P95: {results['latency']['p95_ms']:.3f}ms")
    
    print("\n" + "=" * 50)
    print("Benchmark Complete")
    
    return results


if __name__ == "__main__":
    results = run_all_benchmarks()
    
    # Print summary
    print("\n\nSUMMARY")
    print("=" * 50)
    for test_name, result in results.items():
        print(f"\n{test_name.upper()}:")
        for key, value in result.items():
            if not key.startswith("test"):
                print(f"  {key}: {value}")
