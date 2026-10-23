import urllib.request
import json

req = urllib.request.urlopen("http://localhost:5050/api/experiments")
data = json.loads(req.read().decode())
print(f"Total experiments: {len(data)}")
for exp in data:
    print("--------------------------------------------------")
    print(f"ID: {exp['id']}")
    print(f"Fault: {exp['fault_type']}")
    print(f"Target: {exp['target_service']}")
    print(f"Status: {exp['status']}")
    print(f"Error: {exp['error_message']}")
    print("Recovery verification:", exp.get("result_metrics", {}).get("recovery_verification"))
    during_state = exp.get("result_metrics", {}).get("during", {}).get("container_state")
    print("During state:", during_state)
    after_state = exp.get("result_metrics", {}).get("after", {}).get("container_state")
    print("After state:", after_state)
    after_http = exp.get("result_metrics", {}).get("after", {}).get("http_health")
    print("After http:", after_http)
    after_traffic = exp.get("result_metrics", {}).get("after", {}).get("service_traffic")
    print("After traffic:", after_traffic)
