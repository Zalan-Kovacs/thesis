import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from opensearchpy import OpenSearch, OpenSearchException
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
