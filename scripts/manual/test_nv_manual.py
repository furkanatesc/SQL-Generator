import requests
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def run_embedding_check(model_name):
    from backend.app.llm_client import get_nvidia_api_key
    api_key = get_nvidia_api_key()
        
    url = "https://integrate.api.nvidia.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Generate 50 very large strings to match table serialization
    long_string = "Table: SampleTable | Columns: " + ", ".join([f"col_{i} (VARCHAR)" for i in range(100)])
    payload = {
        "model": model_name,
        "input": [long_string] * 50,
        "encoding_format": "float",
        "input_type": "query"
    }
    
    print(f"Testing {model_name} with batch size 50...")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    run_embedding_check("nvidia/llama-nemotron-embed-1b-v2")
