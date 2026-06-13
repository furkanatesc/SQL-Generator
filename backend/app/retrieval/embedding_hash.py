import hashlib

def compute_summary_hash(summary_text: str, summary_version: str) -> str:
    """
    Computes a deterministic SHA-256 hash of the summary text prefixed by summary version.
    This hash changes whenever the summary representation or summary version changes,
    ensuring robust cache invalidation.
    """
    input_str = f"{summary_version}:{summary_text}"
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest()
