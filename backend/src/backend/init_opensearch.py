import os
import sys

from opensearchpy import OpenSearch, OpenSearchException

HOST = os.getenv("OPENSEARCH_HOST", "localhost")
PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))

client = OpenSearch(
    hosts=[{"host": HOST, "port": PORT}],
    http_compress=True,
    use_ssl=False,
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)

SYSTEM_LOGS_INDEX = "system-logs"
KNOWLEDGE_INDEX = "incident-knowledge"
PIPELINE_NAME = "hybrid-log-pipeline"


def init_system_logs(force_drop: bool = False):
    if client.indices.exists(index=SYSTEM_LOGS_INDEX):
        if force_drop:
            client.indices.delete(index=SYSTEM_LOGS_INDEX)
            print(f"[RESET] '{SYSTEM_LOGS_INDEX}' index deleted.")
        else:
            print(f"[SKIP] '{SYSTEM_LOGS_INDEX}' already exists.")
            return

    index_body = {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "timeStamp": {"type": "date"},
                "service": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "message": {"type": "text"},
                "message_vector": {
                    "type": "knn_vector",
                    "dimension": 384,
                    "method": {
                        "name": "hnsw",
                        "space_type": "innerproduct",
                        "engine": "faiss",
                        "parameters": {"ef_construction": 100, "m": 16},
                    },
                },
            }
        },
    }
    client.indices.create(index=SYSTEM_LOGS_INDEX, body=index_body)
    print(f"[OK] '{SYSTEM_LOGS_INDEX}' index created.")


def init_incident_knowledge():
    if client.indices.exists(index=KNOWLEDGE_INDEX):
        print(f"[SKIP] '{KNOWLEDGE_INDEX}' index már létezik.")
        return

    index_body = {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "problem_message": {"type": "text"},
                "problem_vector": {
                    "type": "knn_vector",
                    "dimension": 384,
                    "method": {
                        "name": "hnsw",
                        "space_type": "innerproduct",
                        "engine": "faiss",
                        "parameters": {"ef_construction": 100, "m": 16},
                    },
                },
                "resolution": {"type": "text"},
                "service": {"type": "keyword"},
                "author": {"type": "keyword"},
                "created_at": {"type": "date"},
            }
        },
    }
    client.indices.create(index=KNOWLEDGE_INDEX, body=index_body)
    print(f"[OK] '{KNOWLEDGE_INDEX}' index created.")


def init_search_pipeline():
    pipeline_body = {
        "description": "Pipeline for BM25 and k-NN score normalization",
        "phase_results_processors": [
            {
                "normalization-processor": {
                    "normalization": {"technique": "min_max"},
                    "combination": {
                        "technique": "arithmetic_mean",
                        "parameters": {"weights": [0.4, 0.6]},
                    },
                }
            }
        ],
    }
    try:
        client.transport.perform_request(
            "PUT", f"/_search/pipeline/{PIPELINE_NAME}", body=pipeline_body
        )
        print(f"[OK] Search Pipeline '{PIPELINE_NAME}' setup succeded.")
    except OpenSearchException as e:
        print(f"[ERROR] Pipeline setup failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    drop_logs = "--reset-logs" in sys.argv
    init_system_logs(force_drop=drop_logs)
    init_incident_knowledge()
    init_search_pipeline()