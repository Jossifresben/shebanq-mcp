"""Deterministic TF-template-to-MQL conversion, for SHEBANQ citation.

A scholar working in a Text-Fabric notebook needs a citable SHEBANQ permalink
for publication. This converts their template to the equivalent MQL with NO
model in the loop: indentation becomes brackets, spaces between constraints
become AND, and the quoting rule comes from the shared catalogue (string
features quoted, enum features bare). The output is validated MQL or a
ConversionError that says plainly what could not be carried over.

Scope is the v1 template grammar tf_validator accepts. Richer TF constructs
(regex ~, quantifier blocks, relational operators) have no MQL equivalent
here and are refused, never silently dropped. Named+ordered siblings (multiple
lines at the same indentation under one parent, each named and fully ordered
via p1 << p2 lines) are converted faithfully to MQL sibling blocks. Unordered
siblings are refused with a fix-it message. Multiple top-level roots are also
refused.
"""
from .feature_reference import FeatureReference
from .tf_validator import _NAMED_LINE, _ORDER_LINE, _PAIR, validate_tf

# Operator constant - swap in ONE place if CI proves << is wrong.
_ORDER_OP = "<<"


class ConversionError(ValueError):
    """The template is invalid or uses constructs outside the v1 grammar."""


def _constraints(otype: str, pairs: str, ref: FeatureReference) -> str:
    parts = []
    for feat, value in _PAIR.findall(pairs):
        if ref.kind_for(feat, otype) == "string":
            if "'" in value or "\\" in value:
                raise ConversionError(
                    f"value {value!r} for string feature '{feat}' contains a "
                    "quote or backslash that cannot be carried into MQL")
            parts.append(f"{feat}='{value}'")
        else:
            parts.append(f"{feat}={value}")
    if not parts:
        return otype
    return f"{otype} " + " AND ".join(parts)


def _topological_sort(names: list[str],
                      pairs: list[tuple[str, str]]) -> list[str]:
    """Kahn's algorithm over the given names and (before, after) pairs.
    Returns the sorted list or raises ConversionError for cycles or partial
    orders (when len(names) >= 3 and not all pairs covered)."""
    name_set = set(names)
    # Build adjacency and in-degree
    succ: dict[str, list[str]] = {n: [] for n in names}
    pred_count: dict[str, int] = {n: 0 for n in names}
    for a, b in pairs:
        succ[a].append(b)
        pred_count[b] += 1

    queue = [n for n in names if pred_count[n] == 0]
    result: list[str] = []
    while queue:
        # For a deterministic total order we take ONE node per step; if
        # there's more than one zero-in-degree node the order is ambiguous.
        if len(queue) > 1:
            raise ConversionError(
                "siblings are only partially ordered; MQL needs a total "
                "order. Add ordering lines to establish a unique sequence.")
        node = queue.pop(0)
        result.append(node)
        for nxt in succ[node]:
            pred_count[nxt] -= 1
            if pred_count[nxt] == 0:
                queue.append(nxt)

    if len(result) != len(names):
        raise ConversionError(
            "ordering is contradictory (a cycle); cannot convert")

    return result


def tf_to_mql(template: str, ref: FeatureReference) -> str:
    """Convert a v1-grammar TF search template to equivalent MQL."""
    # --- Pass 0: separate ordering lines from object lines ---
    # Ordering lines are at column 0 and match name << name.
    # Surface out-of-grammar TF syntax with a specific message before the
    # generic validator complaint (a '~' line also fails _NAMED_LINE).
    ordering_pairs: list[tuple[str, str]] = []   # (before, after) from << lines
    for lineno, raw in enumerate(template.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        # Skip ordering lines in the pre-check; they are valid.
        if _ORDER_LINE.match(line):
            om = _ORDER_LINE.match(line)
            ordering_pairs.append((om.group(1), om.group(2)))
            continue
        if not _NAMED_LINE.match(line):
            raise ConversionError(
                f"line {lineno} ('{line}') uses Text-Fabric syntax that "
                "cannot be converted to MQL here (only "
                "'<object_type> feature=value ...' lines are supported)")

    validation = validate_tf(template, ref)
    if not validation.ok:
        raise ConversionError("; ".join(validation.errors))

    # --- Pass 1: build the indentation tree ---
    # We track for each parent_indent: the list of (name_or_None, otype, pairs,
    # indent) child entries so we can later resolve sibling ordering.
    # Each entry in the stack is: (indent, children_list)
    # children_list items: [name, otype, pairs_str, sub_children_list]

    # We'll build a simple recursive structure then flatten to MQL.
    # node = {"name": str|None, "otype": str, "pairs": str, "children": [node]}

    roots: list[dict] = []
    stack: list[tuple[int, list]] = []  # (indent, children list we append to)

    for raw in template.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _ORDER_LINE.match(line):
            continue  # ordering lines handled separately
        indent = len(raw) - len(raw.lstrip(" "))
        # Close blocks deeper than current indent
        while stack and stack[-1][0] >= indent:
            stack.pop()
        m = _NAMED_LINE.match(line)
        node = {"name": m.group(1), "otype": m.group(2),
                "pairs": m.group(3), "children": []}
        if stack:
            stack[-1][1].append(node)
        else:
            roots.append(node)
        stack.append((indent, node["children"]))

    # Multiple top-level roots are refused.
    if len(roots) > 1:
        raise ConversionError(
            "multiple top-level object blocks cannot be converted: "
            "a Text-Fabric template must have a single root. "
            "Add ordering lines (for example 'p1 << p2') to convert.")

    # --- Pass 2: collect name->node and parent->children mappings ---
    name_to_node: dict[str, dict] = {}
    # For each parent we track: its children list, and which children are named.
    # We need to:
    #  a) refuse multiple unnamed children (unordered sibling)
    #  b) resolve ordering among named children
    #  c) refuse cross-parent ordering

    def _collect_names(node_list: list) -> None:
        for node in node_list:
            if node["name"] is not None:
                name_to_node[node["name"]] = node
            _collect_names(node["children"])

    _collect_names(roots)

    # Validate ordering pairs reference only known names.
    for a, b in ordering_pairs:
        if a not in name_to_node:
            raise ConversionError(
                f"ordering references undefined name '{a}'")
        if b not in name_to_node:
            raise ConversionError(
                f"ordering references undefined name '{b}'")

    # Build parent->child_names map. For each node, check its children.
    # Cross-parent: a << b valid only if a and b are siblings under same parent.
    def _find_parent_groups(node_list: list, parent_id: object
                            ) -> dict[object, list[str]]:
        """Return {parent_id: [child_names...]} for all nodes with >=1 named
        child. Uses id(parent_node) as key; root level uses None."""
        result: dict[object, list[str]] = {}
        named = [c["name"] for c in node_list if c["name"] is not None]
        if named:
            result[parent_id] = named
        for child in node_list:
            result.update(_find_parent_groups(child["children"], id(child)))
        return result

    parent_groups = _find_parent_groups(roots, None)
    # Build reverse: name -> parent_id
    name_to_parent: dict[str, object] = {}
    for pid, names in parent_groups.items():
        for n in names:
            name_to_parent[n] = pid

    # Check cross-parent ordering
    for a, b in ordering_pairs:
        pa = name_to_parent.get(a)
        pb = name_to_parent.get(b)
        if pa != pb:
            raise ConversionError(
                f"ordering pair '{a} {_ORDER_OP} {b}' crosses parent "
                "boundaries; only sibling nodes (children of the same parent) "
                "can be ordered relative to each other")

    # --- Pass 3: sort siblings and emit MQL ---
    # Build a per-parent ordering: apply topological sort using only the pairs
    # that belong to that parent's children.

    def _emit_node(node: dict) -> str:
        """Recursively emit a [otype constraints children...] MQL block."""
        inner_mql = _constraints(node["otype"], node["pairs"], ref)
        children = node["children"]

        if not children:
            return f"[{inner_mql}]"

        # Check if any child is named
        named_children = [c for c in children if c["name"] is not None]
        unnamed_children = [c for c in children if c["name"] is None]

        if len(children) >= 2:
            # Mixed named/unnamed siblings: refuse
            if unnamed_children and named_children:
                raise ConversionError(
                    "sibling lines are unordered; MQL siblings are ordered. "
                    "Add ordering lines (for example 'p1 << p2') to convert.")
            if not named_children:
                # All unnamed and multiple children: unordered siblings
                raise ConversionError(
                    "sibling lines are unordered; MQL siblings are ordered. "
                    "Add ordering lines (for example 'p1 << p2') to convert.")
            # All named: apply topological sort
            child_names = [c["name"] for c in children]
            # Find ordering pairs relevant to this parent
            relevant_pairs = [(a, b) for a, b in ordering_pairs
                              if a in set(child_names) and b in set(child_names)]
            sorted_names = _topological_sort(child_names, relevant_pairs)
            name_to_child = {c["name"]: c for c in children}
            sorted_children = [name_to_child[n] for n in sorted_names]
        else:
            # Single child: no ordering needed
            sorted_children = children

        child_blocks = " .. ".join(_emit_node(c) for c in sorted_children)
        return f"[{inner_mql} {child_blocks}]"

    # Emit roots
    assert len(roots) == 1
    body = _emit_node(roots[0])
    return f"SELECT ALL OBJECTS WHERE {body} GO"
