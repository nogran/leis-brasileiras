"""Read-only fidelity report; a missing source never becomes a synthetic legal record."""
import json

from tools.build_inventory import inventory


def main():
    rows = inventory()
    print(json.dumps({"complete": all(row["complete"] for row in rows), "laws": rows},
                     ensure_ascii=False, indent=2))
    return 0 if all(row["complete"] for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
