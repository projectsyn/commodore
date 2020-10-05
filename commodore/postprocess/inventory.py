import re


class InventoryError(Exception):
    pass


INV_REF = re.compile(r"\$\{([^}]+)\}")


def _resolve_var(inv, m):
    var = m.group(1)
    invpath = var.split(":")
    val = inv["parameters"]
    for elem in invpath:
        val = val.get(elem, None)
        if val is None:
            raise InventoryError(f"Unable to resolve inventory reference {var}")
    return val


def resolve_inventory_vars(inv, args):
    """
    Recursively resolve reclass references in `args`.
    """
    resolved = {}
    for k, v in args.items():
        if isinstance(v, list):
            resolved[k] = map(lambda e: resolve_inventory_vars(inv, e), v)
        elif isinstance(v, dict):
            resolved[k] = resolve_inventory_vars(inv, v)
        elif isinstance(v, str):
            try:
                resolved[k] = INV_REF.sub(lambda m: _resolve_var(inv, m), v)
            except TypeError as e:
                if v.startswith("${") and v.endswith("}"):
                    m = INV_REF.match(v)
                    if m is None:
                        raise InventoryError(f"Error replacing reference: {e}") from e
                    resolved[k] = _resolve_var(inv, m)
                else:
                    raise e
        else:
            resolved[k] = v
    return resolved
