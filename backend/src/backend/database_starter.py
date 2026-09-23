from opensearchpy import OpenSearch

client = OpenSearch(
    hosts = [{"host": "localhost", "port": 9200}]
)

INDEX_NAME = "system-logs"

index_body = {
    "settings": {
        "index": {
            "knn": True
        }
    },
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
          "parameters": {
            "ef_construction": 100,
            "m": 16
          }
        }
      }
    }
  }
}

if client.indices.exists(index=INDEX_NAME):
    client.indices.delete(index=INDEX_NAME)

client.indices.create(index=INDEX_NAME, body=index_body)
print(f"Index '{INDEX_NAME}' created.")

PIPELINE_NAME = "hybrid-log-pipeline"

pipeline_body= {
    "description": "pipeline for BM25 and k-NN point normalization",
    "phase_results_processors": [
        {
            "normalization-processor": {
                "normalization": {
                    "technique": "min_max"
                },
                "combination": {
                    "technique": "arithmetic_mean",
                    "parameters": {
                        "weights": [0.3, 0.7] 
                    }
                }
            }
        }
    ]
}

client.transport.perform_request(
    "PUT",
    f"/_search/pipeline/{PIPELINE_NAME}",
    body=pipeline_body
)
print(f"Search Pipeline '{PIPELINE_NAME}' created.")