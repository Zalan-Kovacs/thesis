import hashlib
import json
import os
import re
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from opensearchpy import OpenSearchException, helpers
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..embeddings import get_embedding, get_embeddings_batch
from ..init_opensearch import KNOWLEDGE_INDEX, PIPELINE_NAME, SYSTEM_LOGS_INDEX, client
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
    r"trace_id=[a-zA-Z0-9\-]+",
    r"user(?:_id)?=\d+",
    r"req-[a-fA-F0-9\-]+",
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
    r"\b(?=[0-9a-fA-F]{8}\b)(?![0-9]{8}\b)[0-9a-fA-F]{8}\b",
    r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
]
IDENTIFIER_REGEX = re.compile("|".join(IDENTIFIER_PATTERNS), re.IGNORECASE)

MASK_SUB_PATTERNS = [
    (re.compile(r"(trace_id=)[a-zA-Z0-9\-]+", re.IGNORECASE), r"\1<ID>"),
    (re.compile(r"(user(?:_id)?=)\d+", re.IGNORECASE), r"\1<ID>"),
    (re.compile(r"\breq-[a-fA-F0-9\-]+\b", re.IGNORECASE), "req-<ID>"),
    (
        re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        ),
        "<UUID>",
    ),
]

def isExactIdentifierQuery(text: str) -> bool:
    return bool(IDENTIFIER_REGEX.search(text))

def mask_identifiers(text: str) -> str:
    masked = text.strip()
    for pattern, repl in MASK_SUB_PATTERNS:
        masked = pattern.sub(repl, masked)
    return masked

def normalize_severity(svr: str | None) -> str:
    if not svr:
        return "INFO"
    val = svr.strip(" :[]").upper()
    if val in ("WARN", "WARNING"):
        return "WARN"
    if val in ("ERR", "ERROR", "FATAL", "SEVERE"):
        return "ERROR"
    return "INFO"

def compute_log_id(service: str, timestamp_iso: str, message: str) -> str:
    raw = f"{service.strip()}|{timestamp_iso.strip()}|{message.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def split_log_line(line: str, separator: str) -> list[str]:
    if separator == " " or separator.strip() == "":
        return re.split(r"\s+", line.strip())
    return line.split(separator)

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
    firstLine = (file.file.readline()).decode("utf-8", errors="replace").strip()
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
            message_val = line

        ts_val = ts_val.strip(" :")
        svr_val = svr_val.strip(" :").upper()
        try:
            parsed_ts = datetime.strptime(ts_val, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("UTC")
            )
        except ValueError:
            parsed_ts = datetime.now(ZoneInfo("UTC"))

        ts_iso = parsed_ts.isoformat()
        doc_id = compute_log_id(service.strip(), ts_iso, message_val)
        template_str = mask_identifiers(message_val)

        lines.append(
            {
                "_index": SYSTEM_LOGS_INDEX,
                "_id": doc_id,
                "_source": {
                    "timeStamp": ts_iso,
                    "service": service,
                    "severity": svr_val or "INFO",
                    "message": message_val,
                    "template": template_str,
                    "source": "historic",
                    "formattedText": f"[{service}] [{svr_val}] {message_val}",
                },
            }
        )
    if lines:
        unique_templates = list({item["_source"]["template"] for item in lines})
        template_vectors = get_embeddings_batch(unique_templates)
        vec_map = dict(zip(unique_templates, template_vectors))
        for item in lines:
            item["_source"]["message_vector"] = vec_map[item["_source"]["template"]]

    try:
        success_count, errors = helpers.bulk(
            client, lines, stats_only=True, raise_on_error=False
        )
        client.indices.refresh(index=SYSTEM_LOGS_INDEX)
    except OpenSearchException as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success", "indexed_count": success_count, "errors_count": errors}


@router.get("/load", response_model=list[LogEntry])
def loadLogs():
    if not os.path.exists(LOGS_PATH):
        raise HTTPException(
            status_code=404, detail="Log file not found. Run log_generator.py first."
        )

    with open(LOGS_PATH, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    logs = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
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
                service=service,
                severity=severity,
                message=message,
                source="historic",
                formattedText=formattedText,
            )
            logs.append(entry)
        except Exception as e:
            print(e)

    return logs

@router.get("/index")
def indexLogs():
    logs = loadLogs()
    if not logs:
        raise HTTPException(status_code=400, detail="No logs To Index")
    templates = [mask_identifiers(log.message) for log in logs]
    unique_templates = list(set(templates))
    vectors = get_embeddings_batch(unique_templates)
    vec_map = dict(zip(unique_templates, vectors))

    actions = []
    for log, template in zip(logs, templates):
        log.message_vector = vec_map[template]
        src = log.model_dump(mode="json")
        src["template"] = template
        doc_id = compute_log_id(log.service, src["timeStamp"], log.message)
        actions.append(
            {
                "_index": SYSTEM_LOGS_INDEX,
                "_id": doc_id,
                "_source": src,
            }
        )

    success_count, errors = helpers.bulk(
        client, actions, stats_only=True, raise_on_error=False
    )
    client.indices.refresh(index=SYSTEM_LOGS_INDEX)
    return {"status": 200, "indexed_count": success_count, "errors_count": errors}

@router.get("/all")
def getAllLogs():
    try:
        response = client.search(
            index=SYSTEM_LOGS_INDEX,
            body={
                "_source": {"excludes": ["message_vector"]},
                "query": {"match_all": {}},
                "size": 100,
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
            index=SYSTEM_LOGS_INDEX,
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
    k: int = Query(default=10, ge=1, le=100)
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
                    "must": [{"match_phrase": {"message": q_clean}}],
                    "filter": filterClauses,
                }
            },
        }
        try:
            response = client.search(
                index=SYSTEM_LOGS_INDEX,
                body=bm25Body,
            )
            return response["hits"]["hits"]
        except OpenSearchException as e:
            raise HTTPException(status_code=500, detail=str(e))

    queryVector = get_embedding(mask_identifiers(q_clean))
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
            index=SYSTEM_LOGS_INDEX,
            body=body,
            params={"search_pipeline": PIPELINE_NAME},
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
            status_code=400, detail="Resolution description cannot be empty."
        )

    clean_msg = data.problem_message.strip()
    masked_msg = mask_identifiers(clean_msg)
    vector = get_embedding(masked_msg)

    doc_id = hashlib.sha256(
        f"{data.service.strip()}|{masked_msg}|{data.resolution.strip()}".encode("utf-8")
    ).hexdigest()

    doc = {
        "problem_message": masked_msg,
        "problem_vector": vector,
        "resolution": data.resolution.strip(),
        "service": data.service.strip(),
        "author": current_user.username,
        "created_at": datetime.now(ZoneInfo("UTC")).isoformat(),
    }

    try:
        res = client.index(
            index=KNOWLEDGE_INDEX,
            id=doc_id,
            body=doc,
            params={"refresh": "true"},
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
def suggest_resolution_for_log(
    message: str,
    threshold: float = 1.80,
    limit: int = Query(default=3, ge=1, le=20),
):
    if not message.strip():
        return {"match": False, "count": 0, "suggestions": []}

    if not client.indices.exists(index=KNOWLEDGE_INDEX):
        return {"match": False, "count": 0, "suggestions": []}

    query_vector = get_embedding(mask_identifiers(message.strip()))

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
        response = client.search(index=KNOWLEDGE_INDEX, body=knn_query)
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

@router.post("/patterns")
def create_saved_pattern(
    pattern: SavePatternPayload,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not pattern.name.strip():
        raise HTTPException(status_code=400, detail="Pattern name cannot be empty.")

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
        raise HTTPException(status_code=404, detail="Pattern not found.")

    db.delete(pattern)
    db.commit()
    return {"status": "deleted"}