"""Invoice Data Validation Agent: completeness (rules.yaml) + internal arithmetic."""
from ..config import load_rules


def data_validation_node(state: dict) -> dict:
    rules = load_rules()
    header, items = state.get("header", {}), state.get("line_items", [])
    missing = [f for f in rules["required_fields"]["header"] if not header.get(f)]
    for i, li in enumerate(items, 1):
        missing += [f"line[{i}].{f}" for f in rules["required_fields"]["line_item"] if li.get(f) in (None, "")]
    # TODO: sum(line totals) == total_amount (minus/plus tax) within tolerance; tax check (tax_difference_percent);
    #       qty*unit_price == line total; invalid currency -> reject (rules.validation_policies).
    return {"missing_fields": missing}
