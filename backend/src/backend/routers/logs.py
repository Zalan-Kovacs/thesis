import json
import os
import re
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from opensearchpy import OpenSearch, OpenSearchException, helpers
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..embeddings import get_embedding, get_embeddings_batch
from .auth import (
    SavedPatternModel,
    SearchHistoryModel,
    UserModel,
    get_current_user,
    get_db,
)

router = APIRouter(
    prefix="/logs",
    tags=["logs"],
    responses={404: {"description": "Not found"}},
)
LOGS_PATH = "../synth_logs.log"

IDENTIFIER_PATTERNS = [
    r"trace_id=[a-fA-F0-9\-]+",
    r"user(?:_id)?=\d+",
    r"\b[0-9a-fA-F]{8}\b",
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
    r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
]
IDENTIFIER_REGEX = re.compile("|".join(IDENTIFIER_PATTERNS), re.IGNORECASE)


def isExactIdentifierQuery(text: str) -> bool:
    return bool(IDENTIFIER_REGEX.search(text))


class LogEntry(BaseModel):
    timeStamp: datetime
    service: str = "sys"
    severity: str = "INFO"
    message: str
    source: str = "historic"
    scenarioTag: str | None = None
    formattedText: str | None = None
    message_vector: list[float] | None = None


class IncidentResolutionCreate(BaseModel):
    problem_message: str
    service: str
    resolution: str

class SearchParamsPayload(BaseModel):
    q: str | None = None
    service: str | None = None
    severity: str | None = None
    dateFrom: str | None = None
    dateTo: str | None = None


class SavePatternPayload(SearchParamsPayload):
    name: str

@router.post("/preview")
def previewFile(file: UploadFile):
    firstLine = (file.file.readline()).decode("utf-8")
    return {"First Line": firstLine}


@router.post("/ingest")
def ingestFile(
    file: UploadFile = File(...),
    service: str = Form(...),
    separator: str = Form(...),
    mapping: str = Form(...),
):
    mapping_dict = json.loads(mapping)
    lines = []
    for line_bytes in file.file:
        line = line_bytes.decode("utf-8").strip()
        if not line:
            continue

        parts = line.split(separator)
        ts_parts = [
            parts[int(i)]
            for i, field in mapping_dict.items()
            if field == "timestamp" and int(i) < len(parts)
        ]
        ts_val = " ".join(ts_parts)
        svr_parts = [
            parts[int(i)]
            for i, field in mapping_dict.items()
            if field == "severity" and int(i) < len(parts)
        ]
        svr_val = " ".join(svr_parts)
        msg_indices = [int(i) for i, f in mapping_dict.items() if f == "message"]
        if msg_indices:
            start_idx = min(msg_indices)
            message_val = separator.join(parts[start_idx:])
        else:
            message_val = ""

        ts_val = ts_val.strip(" :")
        svr_val = svr_val.strip(" :").upper()
        try:
            parsed_ts = datetime.strptime(ts_val, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("UTC")
            )
        except ValueError:
            parsed_ts = datetime.now(ZoneInfo("UTC"))

        lines.append(
            {
                "_index": "system-logs",
                "_source": {
                    "timeStamp": parsed_ts.isoformat(),
                    "service": service,
                    "severity": svr_val or "INFO",
                    "message": message_val,
                    "source": "historic",
                    "formattedText": f"[{service}] [{svr_val}] {message_val}",
                },
            }
        )
    if lines:
        messages = [item["_source"]["message"] for item in lines]
        vectors = get_embeddings_batch(messages)
        for (
            item,
            vec,
        ) in zip(lines, vectors):
            item["_source"]["message_vector"] = vec

    success_count, errors = helpers.bulk(client, lines, stats_only=True)

    return {"status": "success", "indexed_count": success_count, "errors_count": errors}


@router.get("/load", response_model=list[LogEntry])
def loadLogs():
    if not os.path.exists(LOGS_PATH):
        raise HTTPException(
            status_code=404, detail="Log file not found. Run log_generator.py first."
        )

    with open(LOGS_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    logs = []
    for line in lines:
        line = line.strip()

        try:
            parts = line.split(": ")
            if len(parts) >= 3:
                timeStampStr = parts[0]
                severity = parts[1]
                message = "".join(parts[2:])
            else:
                timeStampStr = parts[0]
                severity = "INFO"
                message = parts[1]
            try:
                timeStamp = datetime.strptime(
                    timeStampStr, "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=ZoneInfo("UTC"))
            except ValueError:
                timeStamp = datetime.now(ZoneInfo("UTC"))
            service = "def_svc"
            formattedText = f"[{service}] [{severity}] {message}"
            entry = LogEntry(
                timeStamp=timeStamp,
                severity=severity,
                message=message,
                source="historic",
                formattedText=formattedText,
            )
            logs.append(entry)
        except Exception as e:
            print(e)

    return logs


host = os.getenv("OPENSEARCH_HOST", "localhost")
port = int(os.getenv("OPENSEARCH_PORT", "9200"))
# auth = ('admin', 'Admin123!')
# ca_certs_path = '/full/path/to/root-ca.pem' # Provide a CA bundle if you use intermediate CAs with your root CA.


client = OpenSearch(
    hosts=[{"host": host, "port": port}],
    http_compress=True,
    # http_auth = auth, TODO
    use_ssl=False,  # True TODO ha https lesz
    verify_certs=True,  # True TODO ha auth lesz
    ssl_assert_hostname=False,
    ssl_show_warn=False,
    # ca_certs = ca_certs_path
)


@router.get("/index")
def indexLogs():
    logs = loadLogs()
    if not logs:
        raise HTTPException(status_code=400, detail="No logs To Index")

    messages = [log.message for log in logs]
    vectors = get_embeddings_batch(messages)

    actions = []
    for log, vec in zip(logs, vectors):
        log.message_vector = vec
        actions.append(
            {"_index": "system-logs", "_source": log.model_dump(mode="json")}
        )

    success_count, errors = helpers.bulk(client, actions, stats_only=True)
    return {"status": 200, "indexed_count": success_count, "errors_count": errors}


@router.get("/all")
def getAllLogs():
    try:
        response = client.search(
            index="system-logs",
            body={
                "query": {"match_all": {}},
                "size": 100,  # TODO expand if needed
            },
        )

        return response
    except OpenSearchException as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
def searchLogs(
    q: str | None = None,
    service: str | None = None,
    severity: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
):
    mustClauses = []
    filterClauses = []
    timeRange = {}
    if q and q != "":
        mustClauses.append({"match": {"message": q}})
    if service and service != "":
        filterClauses.append({"term": {"service": service}})
    if severity and severity != "":
        filterClauses.append({"term": {"severity": severity.upper()}})
    if dateFrom and dateFrom != "":
        timeRange["gte"] = dateFrom
    if dateTo and dateTo != "":
        timeRange["lte"] = dateTo
    if timeRange != {}:
        filterClauses.append({"range": {"timeStamp": timeRange}})

    try:
        if mustClauses == [] and filterClauses == []:
            query = {"match_all": {}}
        else:
            bool_query = {}
            if mustClauses != []:
                bool_query["must"] = mustClauses
            if filterClauses != []:
                bool_query["filter"] = filterClauses
            query = {"bool": bool_query}

        response = client.search(
            index="system-logs",
            body={
                "query": query,
                "size": 50,
                "sort": [{"timeStamp": {"order": "desc"}}],
            },
        )
        return response["hits"]["hits"]
    except OpenSearchException as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hybrid-search")
def hybridSearchLogs(
    q: str,
    service: str | None = None,
    severity: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    k: int = 10,
):
    q_clean = q.strip()

    filterClauses = []
    timeRange = {}
    if service and service != "":
        filterClauses.append({"term": {"service": service}})
    if severity and severity != "":
        filterClauses.append({"term": {"severity": severity.upper()}})
    if dateFrom and dateFrom != "":
        timeRange["gte"] = dateFrom
    if dateTo and dateTo != "":
        timeRange["lte"] = dateTo
    if timeRange != {}:
        filterClauses.append({"range": {"timeStamp": timeRange}})

    if isExactIdentifierQuery(q_clean):
        bm25Body = {
            "size": k,
            "_source": {"excludes": ["message_vector"]},
            "query": {
                "bool": {
                    "must": [{"match": {"message": q_clean}}],
                    "filter": filterClauses,
                }
            },
        }
        try:
            response = client.search(
                index="system-logs",
                body=bm25Body,
            )
            return response["hits"]["hits"]
        except OpenSearchException as e:
            raise HTTPException(status_code=500, detail=str(e))

    queryVector = get_embedding(q_clean)
    keywordQuery = {
        "bool": {
            "must": [{"match": {"message": q_clean}}],
            "filter": filterClauses,
        }
    }

    knnSubquery = {"vector": queryVector, "k": k}

    if filterClauses:
        knnSubquery["filter"] = {"bool": {"filter": filterClauses}}

    vectorQuery = {"knn": {"message_vector": knnSubquery}}
    body = {
        "size": k,
        "_source": {"excludes": ["message_vector"]},
        "query": {"hybrid": {"queries": [keywordQuery, vectorQuery]}},
    }
    try:
        response = client.search(
            index="system-logs",
            body=body,
            params={"search_pipeline": "hybrid-log-pipeline"},
        )
        return response["hits"]["hits"]
    except OpenSearchException as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/knowledge/resolve")
def save_incident_resolution(
    data: IncidentResolutionCreate,
    current_user: Annotated[UserModel, Depends(get_current_user)],
):
    if not data.resolution.strip():
        raise HTTPException(
            status_code=400, detail="Resolution Description cannot be empty."
        )

    clean_msg = data.problem_message.strip()
    vector = get_embedding(clean_msg)

    doc = {
        "problem_message": clean_msg,
        "problem_vector": vector,
        "resolution": data.resolution.strip(),
        "service": data.service,
        "author": current_user.username,
        "created_at": datetime.now(ZoneInfo("UTC")).isoformat(),
    }

    try:
        res = client.index(
            index="incident-knowledge", body=doc, params={"refresh": "true"}
        )
        return {
            "status": "success",
            "id": res["_id"],
            "resolution": data.resolution.strip(),
            "author": current_user.username,
        }
    except OpenSearchException as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/suggest")
def suggest_resolution_for_log(message: str, threshold: float = 1.30, limit: int = 3):
    if not message.strip():
        return {"match": False, "suggestion": []}

    query_vector = get_embedding(message.strip())

    knn_query = {
        "size": limit,
        "_source": [
            "problem_message",
            "resolution",
            "author",
            "service",
            "created_at",
        ],
        "query": {
            "knn": {
                "problem_vector": {
                    "vector": query_vector,
                    "k": limit,
                }
            }
        },
    }

    try:
        response = client.search(index="incident-knowledge", body=knn_query)
        hits = response["hits"]["hits"]

        valid_suggestions = []
        for hit in hits:
            score = hit["_score"]
            if score >= threshold:
                src = hit["_source"]
                valid_suggestions.append(
                    {
                        "score": round(score, 4),
                        "resolution": src["resolution"],
                        "author": src["author"],
                        "service": src.get("service"),
                        "original_pattern": src["problem_message"],
                        "created_at": src.get("created_at"),
                    }
                )
        return {
            "match": len(valid_suggestions) > 0,
            "count": len(valid_suggestions),
            "suggestions": valid_suggestions,
        }
    except OpenSearchException as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/history")
def record_search_history(
    params: SearchParamsPayload,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    history_entry = SearchHistoryModel(
        user_id=current_user.id,
        q=params.q,
        service=params.service,
        severity=params.severity,
        date_from=params.dateFrom,
        date_to=params.dateTo,
    )
    db.add(history_entry)
    db.commit()
    return {"status": "ok"}


@router.get("/history")
def get_search_history(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    entries = (
        db.query(SearchHistoryModel)
        .filter(SearchHistoryModel.user_id == current_user.id)
        .order_by(SearchHistoryModel.created_at.desc())
        .limit(10)
        .all()
    )
    return entries


# --- GYAKORI KERESÉSI MINTÁK (PRESETEK) ---


@router.post("/patterns")
def create_saved_pattern(
    pattern: SavePatternPayload,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not pattern.name.strip():
        raise HTTPException(status_code=400, detail="A minta neve nem lehet üres.")

    new_pattern = SavedPatternModel(
        user_id=current_user.id,
        name=pattern.name.strip(),
        q=pattern.q,
        service=pattern.service,
        severity=pattern.severity,
        date_from=pattern.dateFrom,
        date_to=pattern.dateTo,
    )
    db.add(new_pattern)
    db.commit()
    return {"status": "ok", "id": new_pattern.id}


@router.get("/patterns")
def get_saved_patterns(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    patterns = (
        db.query(SavedPatternModel)
        .filter(SavedPatternModel.user_id == current_user.id)
        .order_by(SavedPatternModel.created_at.desc())
        .all()
    )
    return patterns


@router.delete("/patterns/{pattern_id}")
def delete_saved_pattern(
    pattern_id: int,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    pattern = (
        db.query(SavedPatternModel)
        .filter(
            SavedPatternModel.id == pattern_id,
            SavedPatternModel.user_id == current_user.id,
        )
        .first()
    )
    if not pattern:
        raise HTTPException(status_code=404, detail="A minta nem található.")

    db.delete(pattern)
    db.commit()
    return {"status": "deleted"}