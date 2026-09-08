"""Jira-Komponenten flach + virtuelle Ordner wie im SCSCM-Treeview."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from app.config import get_settings


def norm_name(raw: str) -> str:
    return " ".join(str(raw or "").split()).casefold()


@lru_cache(maxsize=1)
def _groups() -> dict[str, dict[str, list[str]]]:
    path = get_settings().component_tree_path
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for root, folders in data.items():
        if not isinstance(folders, dict):
            continue
        packed: dict[str, list[str]] = {}
        for folder, leaves in folders.items():
            if isinstance(leaves, list):
                packed[str(folder)] = [str(leaf) for leaf in leaves]
        out[str(root)] = packed
    return out


def _node(record: dict[str, Any] | None, name: str, *, virtual: bool = False) -> dict[str, Any]:
    rec = record or {}
    return {
        "name": str(rec.get("name") or name),
        "label": str(rec.get("name") or name),
        "description": str(rec.get("description") or "").strip(),
        "virtual": virtual,
        "selectable": not virtual,
        "children": [],
    }


def build_component_tree(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {norm_name(row.get("name") or ""): row for row in records if row.get("name")}
    used: set[str] = set()
    tree: list[dict[str, Any]] = []

    for root_name, folders in _groups().items():
        root_rec = by_key.get(norm_name(root_name))
        root = _node(root_rec, root_name)
        used.add(norm_name(root["name"]))
        for folder_name, leaves in folders.items():
            kids: list[dict[str, Any]] = []
            for leaf in leaves:
                rec = by_key.get(norm_name(leaf))
                if not rec:
                    continue
                kids.append(_node(rec, str(rec.get("name") or leaf)))
                used.add(norm_name(rec.get("name") or leaf))
            if kids:
                folder = _node(None, folder_name, virtual=True)
                folder["children"] = kids
                root["children"].append(folder)
        tree.append(root)

    leftovers = [
        _node(row, str(row.get("name")))
        for row in records
        if row.get("name") and norm_name(row.get("name") or "") not in used
    ]
    leftovers.sort(key=lambda row: (not str(row["name"]).startswith("SCS -"), str(row["name"]).casefold()))
    tree.extend(leftovers)
    return tree


def flatten_tree(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("selectable") and not node.get("virtual"):
            out.append(
                {
                    "name": node["name"],
                    "label": node.get("label") or node["name"],
                    "description": node.get("description") or "",
                }
            )
        out.extend(flatten_tree(list(node.get("children") or [])))
    return out
