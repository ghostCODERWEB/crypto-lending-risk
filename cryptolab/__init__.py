"""Evaluate collateral health, oracle freshness and constrained liquidation scenarios with Decimal arithmetic."""

import json

from decimal import Decimal, localcontext


def number(value):
    n = Decimal(str(value))
    if not n.is_finite() or n < 0:
        raise ValueError("finite nonnegative value required")
    return n


def analyze(data):
    with localcontext() as ctx:
        ctx.prec = 60
        assets = data["assets"]
        now = data["timestamp"]
        max_age = data.get("max_oracle_age", 3600)
        if not isinstance(now, int) or not isinstance(max_age, int) or max_age < 0:
            raise ValueError("invalid time")
        scenarios = data.get("scenarios", [{"name": "base", "price_multipliers": {}}])
        results = []
        for scenario in scenarios:
            total = Decimal(0)
            adjusted = Decimal(0)
            debt = Decimal(0)
            details = []
            for position in data["positions"]:
                symbol = position["asset"]
                asset = assets[symbol]
                updated = asset["updated_at"]
                if updated > now or now - updated > max_age:
                    raise ValueError("stale or future oracle")
                threshold = number(asset["liquidation_threshold"])
                if threshold > 1:
                    raise ValueError("threshold exceeds one")
                price = number(asset["price"]) * number(
                    scenario.get("price_multipliers", {}).get(symbol, 1)
                )
                value = number(position["amount"]) * price
                if position["side"] == "collateral":
                    total += value
                    adjusted += value * threshold
                elif position["side"] == "debt":
                    debt += value
                else:
                    raise ValueError("invalid position side")
                details.append(
                    {"asset": symbol, "side": position["side"], "value": str(value)}
                )
            health = adjusted / debt if debt else None
            close = number(data.get("close_factor", "0.5"))
            bonus = number(data.get("liquidation_bonus", "0.05"))
            if close > 1:
                raise ValueError("close factor exceeds one")
            liquidatable = debt > 0 and adjusted < debt
            repay = (
                min(debt * close, total / (1 + bonus)) if liquidatable else Decimal(0)
            )
            results.append(
                {
                    "name": scenario["name"],
                    "collateral_value": str(total),
                    "adjusted_collateral": str(adjusted),
                    "debt_value": str(debt),
                    "health_factor": str(health) if health is not None else None,
                    "liquidatable": liquidatable,
                    "max_repay_value": str(repay),
                    "seize_value": str(repay * (1 + bonus)),
                    "positions": details,
                }
            )
        return {"scenarios": results}


import argparse
import csv
import io
import sys
from pathlib import Path


def load_input(path):
    raw = Path(path).read_text(encoding="utf-8")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("invalid JSON constant: " + value)

    data = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def flatten(value, prefix=""):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(flatten(item, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(flatten(item, f"{prefix}[{index}]"))
    else:
        rows.append((prefix, json.dumps(value, ensure_ascii=False)))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input file")
    parser.add_argument("--output", help="write result atomically to a file")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    args = parser.parse_args(argv)
    try:
        result = analyze(load_input(args.input))
        if args.format == "json":
            content = (
                json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
            )
        else:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["path", "value"])
            writer.writerows(flatten(result))
            content = buffer.getvalue()
        if args.output:
            import os, tempfile

            target = Path(args.output)
            fd, temporary = tempfile.mkstemp(
                prefix="." + target.name + ".", dir=target.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(content)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        else:
            sys.stdout.write(content)
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
