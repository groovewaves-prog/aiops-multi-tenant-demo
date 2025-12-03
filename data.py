"""
Google Antigravity AIOps Agent - データモジュール
"""
import json
import os
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class NetworkNode:
    id: str
    layer: int
    type: str
    parent_id: Optional[str] = None
    redundancy_group: Optional[str] = None
    internal_redundancy: Optional[str] = None # ★追加: 機器内冗長 (例: "PSU")

def load_topology_from_json(filename: str = "topology.json") -> Dict[str, NetworkNode]:
    topology = {}
    if not os.path.exists(filename): return {}

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        for key, value in raw_data.items():
            node = NetworkNode(
                id=key,
                layer=value.get("layer", 99),
                type=value.get("type", "UNKNOWN"),
                parent_id=value.get("parent_id"),
                redundancy_group=value.get("redundancy_group"),
                internal_redundancy=value.get("internal_redundancy") # ★追加
            )
            topology[key] = node
            
    except Exception as e:
        print(f"Error loading topology: {e}")
        return {}

    return topology

TOPOLOGY = load_topology_from_json()
