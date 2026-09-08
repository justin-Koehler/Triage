from app.services.component_tree import build_component_tree, flatten_tree


def test_builds_vs_folders_and_keeps_other_roots():
    records = [
        {"name": "SCS - VS", "description": "Changes in VS Verantwortung"},
        {"name": "Mobilität", "description": ""},
        {"name": "Klimaneutralität &  Energieautarkie", "description": "Subcomponent V&S"},
        {"name": "Collaborative Innovation", "description": ""},
        {"name": "SCS - Bau", "description": "Changes in Bau Verantwortung"},
        {"name": "CIT", "description": "Changes in CIT Verantwortung"},
    ]
    tree = build_component_tree(records)
    roots = [node["name"] for node in tree]
    assert roots[0] == "SCS - VS"
    assert "SCS - Bau" in roots
    assert "CIT" in roots
    vs = tree[0]
    folders = [node["name"] for node in vs["children"]]
    assert folders == ["Nachhaltigkeit", "Smart Campus"]
    assert vs["children"][0]["virtual"] is True
    leaves = [node["name"] for node in vs["children"][0]["children"]]
    assert "Mobilität" in leaves
    assert "Klimaneutralität &  Energieautarkie" in leaves
    names = [row["name"] for row in flatten_tree(tree)]
    assert "Nachhaltigkeit" not in names
    assert "SCS - VS" in names
    assert "Mobilität" in names
