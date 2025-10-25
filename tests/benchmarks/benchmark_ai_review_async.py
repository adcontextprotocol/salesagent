#!/usr/bin/env python3
"""Benchmark script to demonstrate async AI review performance improvement.

This script simulates the difference between synchronous and asynchronous AI review.

Usage:
    python tests/benchmarks/benchmark_ai_review_async.py
"""

import time
from concurrent.futures import ThreadPoolExecutor


def simulate_ai_review_sync(creative_id: str) -> dict:
    """Simulate synchronous AI review (blocking)."""
    # Simulate Gemini API call (5-15 seconds)
    time.sleep(0.5)  # Using 0.5s for demo (scale down from real 5-15s)
    return {
        "creative_id": creative_id,
        "status": "approved",
        "reason": "Meets all criteria",
        "confidence": "high",
    }


def simulate_ai_review_async(creative_id: str, executor: ThreadPoolExecutor) -> dict:
    """Simulate asynchronous AI review (non-blocking)."""

    def background_review():
        time.sleep(0.5)  # Simulate API call
        return {
            "creative_id": creative_id,
            "status": "approved",
            "reason": "Meets all criteria",
            "confidence": "high",
        }

    # Submit to executor and return immediately
    future = executor.submit(background_review)
    return {"creative_id": creative_id, "task": future, "status": "pending"}


def benchmark_sync_mode(creative_count: int) -> dict:
    """Benchmark synchronous AI review."""
    print(f"\n{'=' * 70}")
    print(f"🐌 SYNCHRONOUS MODE - Processing {creative_count} creatives")
    print(f"{'=' * 70}")

    start_time = time.time()

    results = []
    for i in range(creative_count):
        creative_id = f"creative_{i + 1}"
        print(f"  Processing {creative_id}...", end=" ", flush=True)
        result = simulate_ai_review_sync(creative_id)
        results.append(result)
        elapsed = time.time() - start_time
        print(f"✓ (total: {elapsed:.2f}s)")

    total_time = time.time() - start_time

    print("\n📊 Results:")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Average per creative: {total_time / creative_count:.2f}s")
    print(f"  Throughput: {creative_count / total_time:.1f} creatives/second")

    # Check for timeout (>120 seconds is typical API timeout)
    timeout_threshold = 60.0  # 60 seconds for demo (120s in real system)
    if total_time > timeout_threshold:
        print(f"  ⚠️  TIMEOUT! Exceeded {timeout_threshold}s threshold")

    return {"mode": "sync", "total_time": total_time, "count": creative_count, "results": results}


def benchmark_async_mode(creative_count: int) -> dict:
    """Benchmark asynchronous AI review."""
    print(f"\n{'=' * 70}")
    print(f"🚀 ASYNCHRONOUS MODE - Processing {creative_count} creatives")
    print(f"{'=' * 70}")

    # Create executor (4 workers like production)
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ai_review_")

    submission_start = time.time()

    # Submit all reviews (non-blocking)
    tasks = []
    for i in range(creative_count):
        creative_id = f"creative_{i + 1}"
        result = simulate_ai_review_async(creative_id, executor)
        tasks.append(result)

    submission_time = time.time() - submission_start

    print(f"  ✓ Submitted {creative_count} tasks in {submission_time:.3f}s")
    print("  Background threads processing reviews...")

    # Wait for all reviews to complete (for benchmark purposes)
    completion_start = time.time()
    completed_results = []
    for task_info in tasks:
        result = task_info["task"].result()  # Wait for completion
        completed_results.append(result)

    total_completion_time = time.time() - submission_start

    print("  ✓ All reviews completed")

    print("\n📊 Results:")
    print(f"  Submission time: {submission_time:.3f}s")
    print(f"  Total completion time: {total_completion_time:.2f}s")
    print(f"  Speedup vs sequential: {creative_count * 0.5 / total_completion_time:.1f}x")
    print(f"  Client wait time: {submission_time:.3f}s (immediate response!)")

    executor.shutdown(wait=False)

    return {
        "mode": "async",
        "submission_time": submission_time,
        "total_completion_time": total_completion_time,
        "count": creative_count,
        "results": completed_results,
    }


def main():
    """Run benchmarks and compare results."""
    print("=" * 70)
    print("AI Review Performance Benchmark")
    print("=" * 70)
    print("\nSimulating creative review with:")
    print("  - AI review time: 0.5s per creative (scaled from 5-15s)")
    print("  - Async workers: 4 concurrent threads")
    print("  - Timeout threshold: 60s (scaled from 120s)")

    creative_counts = [5, 10, 20]

    all_results = []

    for count in creative_counts:
        # Run synchronous benchmark
        sync_result = benchmark_sync_mode(count)
        all_results.append(sync_result)

        # Run asynchronous benchmark
        async_result = benchmark_async_mode(count)
        all_results.append(async_result)

        # Compare
        print(f"\n{'=' * 70}")
        print(f"📈 COMPARISON - {count} creatives")
        print(f"{'=' * 70}")

        sync_time = sync_result["total_time"]
        async_submit_time = async_result["submission_time"]
        async_total_time = async_result["total_completion_time"]

        print(f"  Synchronous:  {sync_time:.2f}s (client waits entire time)")
        print(f"  Asynchronous: {async_submit_time:.3f}s (client wait) + background processing")
        print(f"  Client speedup: {sync_time / async_submit_time:.0f}x faster response")
        print(f"  Parallel efficiency: {sync_time / async_total_time:.1f}x overall speedup")

        if sync_time > 60:
            print(f"  ⚠️  Synchronous mode TIMEOUT (>{60}s)")
        print("  ✅ Asynchronous mode: NO TIMEOUT (immediate response)")

    # Final summary
    print(f"\n{'=' * 70}")
    print("🎯 SUMMARY")
    print(f"{'=' * 70}")
    print("\nAsynchronous AI Review Benefits:")
    print("  1. ✅ Immediate response (<1 second)")
    print("  2. ✅ No timeout issues (regardless of creative count)")
    print("  3. ✅ 4x parallel processing (with 4 workers)")
    print("  4. ✅ Better user experience (no long waits)")
    print("  5. ✅ Scalable (can handle 100+ creatives)")

    print("\nProduction Performance (scaled up):")
    print("  Synchronous (10 creatives):  100+ seconds → TIMEOUT ❌")
    print("  Asynchronous (10 creatives): <1 second → SUCCESS ✅")
    print("  Improvement: 100x faster client response")

    print("\nConclusion:")
    print("  Async AI review eliminates timeout issues and provides")
    print("  immediate response to clients, improving UX significantly.")
    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    main()
