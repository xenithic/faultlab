"""
FaultLab resource stress worker script.
Can be executed directly via Python inside target containers as a lightweight,
controlled stress generator when stress-ng is unavailable or as a fallback.
"""
import argparse
import multiprocessing
import os
import signal
import sys
import time

stop_requested = False


def handle_signal(sig, frame):
    global stop_requested
    stop_requested = True
    sys.exit(0)


def cpu_worker(load_percent: int, duration: float):
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    end_time = time.time() + duration
    slice_sec = 0.1
    work_slice = slice_sec * (load_percent / 100.0)
    sleep_slice = slice_sec - work_slice

    while time.time() < end_time and not stop_requested:
        t_start = time.perf_counter()
        while (time.perf_counter() - t_start) < work_slice:
            _ = 2147483647 * 2147483647
        if sleep_slice > 0:
            time.sleep(sleep_slice)


def parse_bytes(mem_str: str) -> int:
    s = str(mem_str).strip().upper()
    if s.endswith("G") or s.endswith("GB"):
        return int(float(s.rstrip("GB")) * 1024 * 1024 * 1024)
    if s.endswith("M") or s.endswith("MB"):
        return int(float(s.rstrip("MB")) * 1024 * 1024)
    if s.endswith("K") or s.endswith("KB"):
        return int(float(s.rstrip("KB")) * 1024)
    try:
        return int(s)
    except ValueError:
        return 128 * 1024 * 1024


def memory_worker(mem_bytes: int, duration: float):
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    end_time = time.time() + duration
    try:
        chunk = bytearray(b"x" * mem_bytes)
    except MemoryError:
        chunk = bytearray(b"x" * (mem_bytes // 2))

    while time.time() < end_time and not stop_requested:
        for i in range(0, len(chunk), 4096):
            chunk[i] = (chunk[i] + 1) % 256
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description="FaultLab Resource Stress Runner")
    parser.add_argument("--type", choices=["cpu", "memory", "both"], default="cpu")
    parser.add_argument("--cpu", type=int, default=1)
    parser.add_argument("--load", type=int, default=80)
    parser.add_argument("--memory", type=str, default="128M")
    parser.add_argument("--duration", type=float, default=10.0)
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    workers = []

    # CPU stress
    if args.type in ("cpu", "both"):
        cpu_count = max(1, min(args.cpu, 4))
        for _ in range(cpu_count):
            p = multiprocessing.Process(
                target=cpu_worker,
                args=(max(1, min(args.load, 100)), args.duration),
            )
            p.daemon = True
            p.start()
            workers.append(p)

    # Memory stress
    if args.type in ("memory", "both"):
        bytes_to_alloc = parse_bytes(args.memory)
        # Safe upper bound 512 MB to prevent host/container OOM
        bytes_to_alloc = max(10 * 1024 * 1024, min(bytes_to_alloc, 512 * 1024 * 1024))
        p = multiprocessing.Process(
            target=memory_worker,
            args=(bytes_to_alloc, args.duration),
        )
        p.daemon = True
        p.start()
        workers.append(p)

    time.sleep(args.duration)
    for p in workers:
        try:
            p.terminate()
            p.join(timeout=0.5)
        except Exception:
            pass


if __name__ == "__main__":
    main()
