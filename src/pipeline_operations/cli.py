"""Inspect local pipeline run history, checkpoints, and partition locks."""

import argparse
import json

from .config import OperationsSettings
from .repository import OperationsRepository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status",))
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    with OperationsRepository(OperationsSettings.from_env()) as repository:
        print(json.dumps(repository.inspect(args.limit), indent=2, default=str))


if __name__ == "__main__":
    main()
