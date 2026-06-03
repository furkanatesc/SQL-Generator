from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery
from app.database import get_config

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

def verify_api_key(
    api_key_h: str = Security(api_key_header),
    api_key_q: str = Security(api_key_query)
):
    api_key = api_key_h or api_key_q
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials. Missing API Key."
        )
        
    stored_key = get_config("api_key")
    if not stored_key:
        import os
        stored_key = os.getenv("NL2SQL_API_KEY")
    if not stored_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API Key not configured in system settings."
        )
    if api_key != stored_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials. Invalid API Key."
        )
    return api_key
