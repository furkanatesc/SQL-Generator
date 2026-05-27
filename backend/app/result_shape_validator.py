from typing import Any
from app.sql_execution_errors import SqlExecutionError

class ResultShapeValidator:
    """
    Validates that database execution results conform strictly to the list[dict[str, Any]] shape,
    raising structured SqlExecutionErrors for any invalid formatting detected.
    """
    @staticmethod
    def validate(rows: Any) -> None:
        """
        Validates that `rows` is a list of dictionaries with string keys.
        """
        if not isinstance(rows, list):
            raise SqlExecutionError(
                code="invalid_result_shape",
                message=f"Execution result must be a list, got {type(rows).__name__}",
                stage="sql_execution",
                details={"value_preview": str(rows)[:500]},
            )

        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                raise SqlExecutionError(
                    code="invalid_result_shape",
                    message=f"Row at index {idx} is not a dictionary, got {type(row).__name__}",
                    stage="sql_execution",
                    details={"index": idx, "row_preview": str(row)[:500]},
                )

            for key in row.keys():
                if not isinstance(key, str):
                    raise SqlExecutionError(
                        code="invalid_result_shape",
                        message=f"Row at index {idx} contains non-string key: {type(key).__name__}",
                        stage="sql_execution",
                        details={
                            "index": idx,
                            "invalid_key": str(key)[:100],
                            "key_type": type(key).__name__,
                        },
                    )

def validate_result_shape(rows: Any) -> None:
    """
    Functional wrapper for ResultShapeValidator.
    """
    ResultShapeValidator.validate(rows)
