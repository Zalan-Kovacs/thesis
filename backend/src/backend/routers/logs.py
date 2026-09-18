import os, json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, UploadFile, Form, File
from opensearchpy import OpenSearch, OpenSearchException, helpers
from pydantic import BaseModel

router = APIRouter(
    prefix="/logs",
    tags=["logs"],
    responses={404: {"description": "Not found"}},
)
LOGS_PATH = "../synth_logs.log"

class LogEntry(BaseModel):
    timeStamp: datetime
    service: str = "sys"
    severity: str = "INFO"
    message: str
    source: str = "historic"
    scenarioTag: str | None = None
    formattedText: str | None = None

@router.post("/preview")
def previewFile(file: UploadFile):
    firstLine = (file.file.readline()).decode("utf-8")
    return {"First Line": firstLine}

@router.post("/ingest")
def ingestFile(
    file: UploadFile = File(...),
    service: str = Form(...),
    separator: str = Form(...),
    mapping: str = Form(...)):
    mapping_dict = json.loads(mapping)
    lines = []
    for line_bytes in file.file:
        line = line_bytes.decode("utf-8").strip()
        if not line:
            continue

        parts = line.split(separator)
        ts_parts = [parts[int(i)] for i, field in mapping_dict.items() if field == "timestamp" and int(i) < len(parts)]
        ts_val = " ".join(ts_parts)
        svr_parts = [parts[int(i)] for i, field in mapping_dict.items() if field == "severity" and int(i) < len(parts)]
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

        lines.append({
            "_index": "system-logs",
            "_source": {
                "timeStamp": parsed_ts.isoformat(),
                "service": service,
                "severity": svr_val or "INFO",
                "message": message_val,
                "source": "historic",
                "formattedText": f"[{service}] [{svr_val}] {message_val}"
            }
        })

    success_count, errors = helpers.bulk(client, lines, stats_only=True)

    return {
        "status": "success",
        "indexed_count": success_count,
        "errors_count": errors
    }


@router.get("/load", response_model=list[LogEntry])
def loadLogs():
    if not os.path.exists(LOGS_PATH):
        raise HTTPException(
                    status_code=404, detail="Log file not found. Run log_generator.py first.")
    
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
                timeStamp = datetime.strptime(timeStampStr, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=ZoneInfo("UTC")
                )
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
    

host = 'localhost'
port = 9200
#auth = ('admin', 'Admin123!')
#ca_certs_path = '/full/path/to/root-ca.pem' # Provide a CA bundle if you use intermediate CAs with your root CA.


client = OpenSearch(
    hosts = [{'host': host, 'port': port}],
    http_compress = True,
    #http_auth = auth, TODO
    use_ssl = False, #True TODO ha https lesz
    verify_certs = True, #True TODO ha auth lesz
    ssl_assert_hostname = False,
    ssl_show_warn = False,
    #ca_certs = ca_certs_path
)


@router.get("/index")
def indexLogs():
    logs = loadLogs()
    if not logs:
        raise HTTPException(status_code=400, detail="No logs To Index")
    errors = []
    for log in logs:
        try:
            client.index(
                index = 'system-logs',
                body = log.model_dump(mode = "json")
            )
        except OpenSearchException as e:
            errors.append(str(e))

    return {"status": 200, "count": len(logs)-len(errors), "errors_count": len(errors), "errors": errors}


@router.get("/all")
def getAllLogs():
    try:
        response = client.search(
            index="system-logs",
            body={
                "query": {
                    "match_all": {}
                },
                "size": 100 #TODO expand if needed
            }
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
        filterClauses.append({"term": {"service.keyword": service}})
    if severity and severity != "":
        filterClauses.append({"term": {"severity.keyword": severity.upper()}})
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
                "sort": [
                    {"timeStamp": {"order": "desc"}}
                ]
            }
        )
        return response["hits"]["hits"]
    except OpenSearchException as e:
        raise HTTPException(status_code=500, detail=str(e))
