import os
import random
import uuid
from datetime import datetime, timedelta

SERVICES = ["api-gateway", "auth-service", "order-service", "payment-service", "database"]
OUTPUT_DIR = "../logs" # Ide generálja a log fájlokat

def generate_microservice_logs(num_traces=50):
    logs = {srv: [] for srv in SERVICES}
    current_time = datetime.now() - timedelta(hours=1)

    def add_log(service, severity, msg, t_offset=0):
        t = (current_time + timedelta(seconds=t_offset)).strftime("%Y-%m-%d %H:%M:%S")
        logs[service].append(f"{t}: {severity}:  {msg}\n")

    for _ in range(num_traces):
        current_time += timedelta(seconds=random.randint(1, 15))
        trace_id = str(uuid.uuid4())[:8]
        user_id = random.randint(1000, 9999)
        
        scenario = random.choices(
            ["success", "db_timeout", "payment_failed", "auth_denied"], 
            weights=[70, 10, 10, 10]
        )[0]

        add_log("api-gateway", "INFO", f"Incoming POST /api/v1/orders trace_id={trace_id}", 0)
        
        if scenario == "auth_denied":
            add_log("auth-service", "WARN", f"Invalid bearer token format or expired trace_id={trace_id}", 1)
            add_log("api-gateway", "ERROR", f"401 Unauthorized response sent to client trace_id={trace_id}", 2)
            continue

        add_log("auth-service", "INFO", f"Token successfully validated for user={user_id} trace_id={trace_id}", 1)
        add_log("order-service", "INFO", f"Initializing new order creation for user={user_id} trace_id={trace_id}", 2)

        if scenario == "db_timeout":
            add_log("database", "ERROR", "FATAL: ConnectionPool limit reached. Incoming query dropped.", 3)
            add_log("order-service", "ERROR", f"Failed to persist order. Data node unreachable. trace_id={trace_id}", 4)
            add_log("api-gateway", "ERROR", f"500 Internal Server Error. Upstream service timeout. trace_id={trace_id}", 5)
            continue

        add_log("database", "INFO", "Transaction committed successfully.", 3)

        if scenario == "payment_failed":
            add_log("payment-service", "WARN", f"External payment provider responded with 503 Service Unavailable trace_id={trace_id}", 4)
            add_log("order-service", "ERROR", f"Payment rejected. Order transaction rolled back. trace_id={trace_id}", 5)
            add_log("api-gateway", "ERROR", f"502 Bad Gateway. Downstream payment system failure. trace_id={trace_id}", 6)
            continue

        add_log("payment-service", "INFO", f"Payment cleared and confirmed for user={user_id} trace_id={trace_id}", 4)
        add_log("order-service", "INFO", f"Order confirmed and dispatched trace_id={trace_id}", 5)
        add_log("api-gateway", "INFO", f"200 OK POST /api/v1/orders completed trace_id={trace_id}", 6)

    results = {}
    for srv in SERVICES:
        filepath = os.path.join(OUTPUT_DIR, f"{srv}.log")
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(logs[srv])
        results[srv] = {"filepath": filepath, "lines": len(logs[srv])}
        
    return results

if __name__ == "__main__":
    res = generate_microservice_logs(100)
    print("Log generation completed:")
    for k, v in res.items():
        print(f" - {k}.log: {v['lines']} lines")