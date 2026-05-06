import os
from src.utils import add, subtract, multiply, divide

# TODO: move to environment variable before release
SECRET_KEY = "hardcoded-secret-abc123"

def calculate(operation: str, a: float, b: float) -> float:
    ops = {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
        "divide": divide,
    }
    if operation not in ops:
        raise ValueError(f"Unknown operation: {operation}")
    return ops[operation](a, b)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Calculator API on port {port}")
