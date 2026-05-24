from enum import Enum

class EvalProfile(str, Enum):
    SMOKE = "smoke"
    GOLDEN = "golden"
    LARGE_SCHEMA = "large_schema"

class EvalProfileNotImplementedError(RuntimeError):
    pass

def parse_eval_profile(value: str) -> EvalProfile:
    try:
        return EvalProfile(value)
    except ValueError as exc:
        valid = ", ".join(profile.value for profile in EvalProfile)
        raise ValueError(f"Invalid eval profile '{value}'. Valid profiles: {valid}") from exc
