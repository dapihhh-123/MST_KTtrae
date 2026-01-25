from fastapi import APIRouter
import datetime
import platform
import sys

router = APIRouter()

@router.get("/runtime/spec")
def get_runtime_spec():
    return {
        "python": sys.version.split(" ")[0],
        "platform": platform.platform(),
        "timestamp": datetime.datetime.now().isoformat()
    }

@router.get("/selfcheck")
def selfcheck():
    return {
        "ok": True,
        "timestamp": datetime.datetime.now().isoformat()
    }
