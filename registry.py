# -*- coding: utf-8 -*-
"""
Tenant/Network Registry (minimal + future-proof)

Canonical layout:
  ./tenants/<TENANT>/networks/<NETWORK>/topology.json
  ./tenants/<TENANT>/networks/<NETWORK>/configs/

This module centralizes:
- tenant/network discovery
- topology path + config dir resolution
- topology loading
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from data import load_topology_from_json, NetworkNode


@dataclass(frozen=True)
class TenantNetworkPaths:
    tenant_id: str
    network_id: str
    topology_path: Path
    config_dir: Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _tenants_root() -> Path:
    return _project_root() / "tenants"


def list_tenants() -> List[str]:
    troot = _tenants_root()
    if not troot.exists():
        return ["A", "B"]
    tenants = sorted([p.name for p in troot.iterdir() if p.is_dir() and not p.name.startswith(".")])
    return tenants or ["A", "B"]


def list_networks(tenant_id: str) -> List[str]:
    nroot = _tenants_root() / tenant_id / "networks"
    if not nroot.exists():
        return ["default"]
    nets = sorted([p.name for p in nroot.iterdir() if p.is_dir() and not p.name.startswith(".")])
    return nets or ["default"]


def get_paths(tenant_id: str, network_id: str) -> TenantNetworkPaths:
    topo = _tenants_root() / tenant_id / "networks" / network_id / "topology.json"
    cfg = _tenants_root() / tenant_id / "networks" / network_id / "configs"
    return TenantNetworkPaths(tenant_id, network_id, topo, cfg)


def topology_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def load_topology(topology_path: Path) -> Dict[str, NetworkNode]:
    return load_topology_from_json(str(topology_path))
