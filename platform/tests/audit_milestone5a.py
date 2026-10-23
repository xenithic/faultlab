"""
FaultLab Milestone 5A Independent End-to-End Safety and API Audit Script.
Executes live experiments against the running Flask API, verifying all 5 fault types,
bounds enforcement, protected infrastructure rejection, concurrency locks, cancellation,
and cleanup verification.
"""
import time
import json
import urllib.request
import urllib.error

API_BASE = "http://127.0.0.1:5050/api"

def api_call(path, method="GET", payload=None):
    url = f"{API_BASE}{path}"
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"error": err_body}

def wait_for_terminal(exp_id, timeout_sec=60):
    start_t = time.time()
    while time.time() - start_t < timeout_sec:
        status_code, data = api_call(f"/experiments/{exp_id}")
        assert status_code == 200, f"Failed to get experiment {exp_id}"
        exp_status = data.get("status")
        if exp_status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(1)
    raise TimeoutError(f"Experiment {exp_id} did not reach terminal state within {timeout_sec}s")

def run_audit():
    print("=== FAULTLAB MILESTONE 5A SAFETY & END-TO-END AUDIT ===")
    
    # 0. Health & Target Verification
    code, health_data = api_call("/health")
    print(f"[0] Health check: status {code}, service={health_data.get('service')}")
    assert code == 200 and health_data.get("status") == "healthy"

    code, targets = api_call("/targets")
    assert code == 200 and len(targets) > 0, "No targets found"
    target = targets[0]
    target_id = target["id"]
    print(f"[0] Using Target #{target_id} ({target['name']}), status={target['validation_status']}")

    # --- PART 1: NEGATIVE & FAILURE PATH AUDIT ---
    print("\n--- PART 1: SECURITY & BOUNDS AUDIT ---")
    
    # 1.1 Unknown fault type rejection
    code, res = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "product-service",
        "fault_type": "arbitrary_kernel_attack",
        "parameters": {"duration_seconds": 10}
    })
    print(f"[1.1] Unknown fault rejection: HTTP {code} (Expected 400)")
    assert code == 400, f"Expected 400, got {code}: {res}"

    # 1.2 Target service not in allowlist
    code, res = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "unauthorized-external-db",
        "fault_type": "service_pause",
        "parameters": {"duration_seconds": 10}
    })
    print(f"[1.2] Unauthorized service rejection: HTTP {code} (Expected 400)")
    assert code == 400, f"Expected 400, got {code}: {res}"

    # 1.3 Target protected infrastructure (postgres) rejection
    code, res = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "postgres",
        "fault_type": "service_failure",
        "parameters": {"duration_seconds": 10}
    })
    print(f"[1.3] Protected infrastructure (postgres) rejection: HTTP {code} (Expected 400)")
    assert code == 400, f"Expected 400, got {code}: {res}"

    # 1.4 Latency bounds rejection (negative or > 10000ms)
    code, res = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "product-service",
        "fault_type": "latency",
        "parameters": {"latency_ms": 25000, "duration_seconds": 5}
    })
    print(f"[1.4] Excessive latency rejection (25000ms): HTTP {code} (Expected 400)")
    assert code == 400, f"Expected 400, got {code}: {res}"

    # 1.5 Resource stress bounds rejection (workers > 4, cpu_load > 100)
    code, res = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "payment-service",
        "fault_type": "resource_stress",
        "parameters": {"cpu_workers": 64, "cpu_load": 150, "duration_seconds": 5}
    })
    print(f"[1.5] Excessive CPU workers/load rejection: HTTP {code} (Expected 400)")
    assert code == 400, f"Expected 400, got {code}: {res}"

    # 1.6 HTTP error invalid status code rejection
    code, res = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "order-service",
        "fault_type": "http_error",
        "parameters": {"error_code": 999, "duration_seconds": 5}
    })
    print(f"[1.6] Invalid HTTP status code rejection (999): HTTP {code} (Expected 400)")
    assert code == 400, f"Expected 400, got {code}: {res}"

    # 1.7 Duration bounds rejection (> 300s or < 1s)
    code, res = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "inventory-service",
        "fault_type": "service_pause",
        "parameters": {"duration_seconds": 3600}
    })
    print(f"[1.7] Excessive duration rejection (3600s): HTTP {code} (Expected 400)")
    assert code == 400, f"Expected 400, got {code}: {res}"

    # --- PART 2: LIVE EXPERIMENT EXECUTION ACROSS ALL 5 FAULTS ---
    print("\n--- PART 2: LIVE EXPERIMENT EXECUTION (ALL 5 FAULTS) ---")
    fault_scenarios = [
        {
            "fault_type": "latency",
            "service": "product-service",
            "params": {"latency_ms": 200, "jitter_ms": 20, "duration_seconds": 4, "recovery_timeout": 10},
            "desc": "Network Latency Injection"
        },
        {
            "fault_type": "http_error",
            "service": "order-service",
            "params": {"error_code": 503, "error_rate": 1.0, "duration_seconds": 4, "recovery_timeout": 10},
            "desc": "HTTP 503 Error Injection"
        },
        {
            "fault_type": "resource_stress",
            "service": "payment-service",
            "params": {"stress_type": "both", "cpu_workers": 1, "cpu_load": 40, "memory_bytes": "32M", "duration_seconds": 4, "recovery_timeout": 10},
            "desc": "CPU/Memory Resource Stress"
        },
        {
            "fault_type": "service_pause",
            "service": "inventory-service",
            "params": {"duration_seconds": 4, "recovery_timeout": 10},
            "desc": "Cgroups Service Pause"
        },
        {
            "fault_type": "service_failure",
            "service": "api-gateway",
            "params": {"stop_timeout": 3, "duration_seconds": 4, "recovery_timeout": 15},
            "desc": "SIGTERM Service Failure & Restart"
        },
    ]

    results_table = []

    for sc in fault_scenarios:
        print(f"\n>> Testing Live Fault: {sc['fault_type']} on {sc['service']} ({sc['desc']})...")
        # 1. Create Experiment
        code, exp = api_call("/experiments", "POST", {
            "target_id": target_id,
            "target_service": sc["service"],
            "fault_type": sc["fault_type"],
            "parameters": sc["params"]
        })
        assert code == 201, f"Failed to create experiment for {sc['fault_type']}: {exp}"
        exp_id = exp["id"]
        print(f"   Created Experiment #{exp_id} [Status: {exp['status']}]")

        # 2. Start Experiment
        code, start_res = api_call(f"/experiments/{exp_id}/start", "POST")
        assert code in (200, 202), f"Failed to start experiment #{exp_id}: {start_res}"
        print(f"   Started Experiment #{exp_id} (HTTP {code})...")

        # 3. Wait for lifecycle completion
        final_exp = wait_for_terminal(exp_id, timeout_sec=40)
        status = final_exp["status"]
        metrics = final_exp.get("result_metrics") or {}
        recov = metrics.get("recovery_verification") or {}
        cleanup = metrics.get("cleanup") or {}
        
        print(f"   Outcome: Status={status}, Verified={recov.get('verified')}, RecoveryTime={recov.get('recovery_time_seconds')}s")
        print(f"   Evidence: {recov.get('evidence')}")
        print(f"   Cleanup Success: {cleanup.get('success')}")

        assert status == "completed", f"Experiment #{exp_id} failed: {final_exp.get('error_message')}"
        assert recov.get("verified") is True, f"Recovery not verified: {recov}"
        assert cleanup.get("success") is True, f"Cleanup failed: {cleanup}"

        results_table.append({
            "fault_type": sc["fault_type"],
            "service": sc["service"],
            "status": status,
            "recovery_verified": recov.get("verified"),
            "recovery_time": recov.get("recovery_time_seconds"),
            "cleanup_success": cleanup.get("success")
        })

    # --- PART 3: CONCURRENCY & CANCELLATION AUDIT ---
    print("\n--- PART 3: CONCURRENCY & CANCELLATION AUDIT ---")
    
    # 3.1 Start an experiment and cancel it while active
    code, exp_to_cancel = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "product-service",
        "fault_type": "latency",
        "parameters": {"latency_ms": 300, "duration_seconds": 15, "recovery_timeout": 10}
    })
    c_id = exp_to_cancel["id"]
    api_call(f"/experiments/{c_id}/start", "POST")
    time.sleep(1.5)  # Let it enter 'running' state
    
    code, cancel_res = api_call(f"/experiments/{c_id}/cancel", "POST")
    print(f"[3.1] Cancellation requested for Experiment #{c_id}: HTTP {code}")
    assert code == 200, f"Cancel failed: {cancel_res}"
    
    cancelled_exp = wait_for_terminal(c_id, timeout_sec=20)
    print(f"[3.1] Cancelled experiment state: {cancelled_exp['status']}")
    assert cancelled_exp["status"] == "cancelled", f"Expected cancelled status, got {cancelled_exp['status']}"
    assert cancelled_exp.get("result_metrics", {}).get("cleanup", {}).get("success") is True, "Cleanup failed upon cancellation"

    # 3.2 Concurrent experiments against the same target container
    # Start experiment A
    code, exp_a = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "order-service",
        "fault_type": "http_error",
        "parameters": {"error_code": 500, "duration_seconds": 10}
    })
    api_call(f"/experiments/{exp_a['id']}/start", "POST")
    
    # Attempt to start experiment B on the same target while A is running
    code, exp_b = api_call("/experiments", "POST", {
        "target_id": target_id,
        "target_service": "order-service",
        "fault_type": "latency",
        "parameters": {"latency_ms": 100, "duration_seconds": 5}
    })
    code_start_b, res_b = api_call(f"/experiments/{exp_b['id']}/start", "POST")
    print(f"[3.2] Concurrent start attempt on same target: HTTP {code_start_b} (Expected 409 Conflict)")
    assert code_start_b == 409, f"Expected 409 Conflict, got {code_start_b}: {res_b}"

    # Wait for A to complete
    wait_for_terminal(exp_a['id'], timeout_sec=20)

    print("\n=== AUDIT SUMMARY RESULTS ===")
    for r in results_table:
        print(f"Fault: {r['fault_type']:<16} Service: {r['service']:<18} Status: {r['status']:<10} RecovVerified: {r['recovery_verified']} ({r['recovery_time']}s) Cleanup: {r['cleanup_success']}")
    print("\nALL AUDIT VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_audit()
