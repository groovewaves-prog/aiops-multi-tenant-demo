# -*- coding: utf-8 -*-
"""
app_cards_multitenant_v3_statusboard_delta_maint.py

Step1: 全社一覧「状態ボード」（停止→劣化→要注意→正常）
Step2: デルタ表示（変化があった tenant だけを強調）
Step3: Maintenance 中 tenant のグレーアウト（最小版：手動フラグ）

注意:
- HTML/CSS は使いません（Streamlit 標準のみ + 絵文字）。
- このファイルは「上部の全社一覧ボード」を中心に実装しています。
  既存のコックピット（表・トポロジ・AI Analyst Report 等）は、
  このファイル末尾の案内どおり “元の app.py のブロックをそのまま貼り付け” してください。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from inference_engine import LogicalRCA
from logic import simulate_cascade_failure

from registry import (
    list_tenants,
    list_networks,
    get_paths,
    load_topology,
    topology_mtime,
)

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="AIOps Incident Cockpit", layout="wide")

# -----------------------------
# Labels (JP)
# -----------------------------
STATUS_ORDER = ["停止", "劣化", "要注意", "正常"]  # 左→右（優先度が高い順）
STATUS_LABELS = {
    "Down": "停止",
    "Degraded": "劣化",
    "Watch": "要注意",
    "Good": "正常",
}
STATUS_ICON = {
    "停止": "🟥",
    "劣化": "🟧",
    "要注意": "🟨",
    "正常": "🟩",
}

# デルタ表示の「対象期間」表記（最小版）
DELTA_WINDOW_MIN = 15


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def display_company(tenant_id: str) -> str:
    return f"{tenant_id}社"


# -----------------------------
# Helpers
# -----------------------------
def _node_type(node: Any) -> str:
    if node is None:
        return "UNKNOWN"
    if isinstance(node, dict):
        return str(node.get("type", "UNKNOWN"))
    return str(getattr(node, "type", "UNKNOWN"))


def _node_layer(node: Any) -> int:
    if node is None:
        return 999
    if isinstance(node, dict):
        try:
            return int(node.get("layer", 999))
        except Exception:
            return 999
    try:
        return int(getattr(node, "layer", 999))
    except Exception:
        return 999


def find_target_node_id(
    topology: Dict[str, Any],
    node_type: Optional[str] = None,
    layer: Optional[int] = None,
) -> Optional[str]:
    for node_id, node in topology.items():
        if node_type and _node_type(node) != node_type:
            continue
        if layer is not None and _node_layer(node) != layer:
            continue
        return node_id
    return None


def _make_alarms(topology: Dict[str, Any], scenario: str):
    if scenario == "WAN全回線断":
        nid = find_target_node_id(topology, node_type="ROUTER")
        return simulate_cascade_failure(nid, topology) if nid else []
    if scenario == "FW片系障害":
        nid = find_target_node_id(topology, node_type="FIREWALL")
        return simulate_cascade_failure(nid, topology, "Power Supply: Single Loss") if nid else []
    if scenario == "L2SWサイレント障害":
        nid = find_target_node_id(topology, node_type="SWITCH", layer=4)
        return simulate_cascade_failure(nid, topology, "Link Degraded") if nid else []
    return []


def _health_from_alarm_count(n: int) -> str:
    if n == 0:
        return "Good"
    if n < 5:
        return "Watch"
    if n < 15:
        return "Degraded"
    return "Down"


@st.cache_data(show_spinner=False)
def _summarize_one_scope(tenant_id: str, network_id: str, scenario: str, mtime: float) -> Dict[str, Any]:
    paths = get_paths(tenant_id, network_id)
    topology = load_topology(paths.topology_path)

    alarms = _make_alarms(topology, scenario)
    alarm_count = len(alarms)
    health = _health_from_alarm_count(alarm_count)

    suspected = None
    if alarms:
        try:
            rca = LogicalRCA(topology, config_dir=str(paths.config_dir))
            res = rca.analyze(alarms) or []
            if res and isinstance(res, list) and isinstance(res[0], dict):
                suspected = res[0].get("id")
        except Exception:
            suspected = None

    return {
        "tenant": tenant_id,
        "network": network_id,
        "health": health,
        "alarms": alarm_count,
        "suspected": suspected,
    }


def _collect_all_scopes(scenario: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for t in list_tenants():
        for n in list_networks(t):
            p = get_paths(t, n)
            rows.append(_summarize_one_scope(t, n, scenario, topology_mtime(p.topology_path)))
    return rows


def _delta_key(r: Dict[str, Any]) -> str:
    return f"{r['tenant']}::{r['network']}"


def _compute_delta(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if "allco_prev" not in st.session_state:
        st.session_state.allco_prev = {}
        st.session_state.allco_prev_ts = _now_iso()

    prev: Dict[str, Dict[str, Any]] = st.session_state.allco_prev
    out: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        k = _delta_key(r)
        p = prev.get(k)
        if p is None:
            out[k] = {"delta": None, "prev_alarms": None, "prev_health": None}
            continue

        d_alarms = int(r["alarms"]) - int(p.get("alarms", 0))
        d_health = (p.get("health") != r.get("health"))
        if d_alarms == 0 and not d_health:
            out[k] = {"delta": None, "prev_alarms": p.get("alarms"), "prev_health": p.get("health")}
        else:
            out[k] = {
                "delta": {
                    "alarms": d_alarms,
                    "health_changed": d_health,
                    "window_min": DELTA_WINDOW_MIN,
                },
                "prev_alarms": p.get("alarms"),
                "prev_health": p.get("health"),
            }

    st.session_state.allco_prev = {
        _delta_key(r): {"alarms": r["alarms"], "health": r["health"]} for r in rows
    }
    st.session_state.allco_prev_ts = _now_iso()

    return out


def _status_jp(health_internal: str) -> str:
    return STATUS_LABELS.get(health_internal, "要注意")


def _status_badge_jp(status_jp: str) -> str:
    icon = STATUS_ICON.get(status_jp, "🟨")
    return f"{icon} {status_jp}"


def _maintenance_map() -> Dict[str, bool]:
    if "maint_flags" not in st.session_state:
        st.session_state.maint_flags = {}
    return st.session_state.maint_flags


def _render_status_board(rows: List[Dict[str, Any]]):
    st.subheader("🏢 全社一覧")
    st.caption("左から優先度が高い順（停止 → 劣化 → 要注意 → 正常）。クリック操作を必要としない 状態ボードです。")

    maint = _maintenance_map()
    deltas = _compute_delta(rows)

    buckets: Dict[str, List[Dict[str, Any]]] = {k: [] for k in STATUS_ORDER}
    for r in rows:
        status = _status_jp(r["health"])
        buckets[status].append(r)

    col_down, col_degraded, col_watch, col_good = st.columns(4)
    col_map = {"停止": col_down, "劣化": col_degraded, "要注意": col_watch, "正常": col_good}

    def _render_bucket(col, status_jp: str):
        items = buckets[status_jp]
        items.sort(key=lambda x: x["alarms"], reverse=True)

        with col:
            st.markdown(f"### {_status_badge_jp(status_jp)}  **{len(items)}**")
            if not items:
                st.caption("（該当なし）")
                return

            max_show = 10
            for r in items[:max_show]:
                tenant = r["tenant"]
                network = r["network"]
                key = _delta_key(r)

                is_maint = bool(maint.get(tenant, False))

                prefix = "🛠️ " if is_maint else ""
                st.write(f"**{prefix}{display_company(tenant)} / {network}**")

                d = deltas.get(key, {}).get("delta")
                if d is not None:
                    da = int(d["alarms"])
                    arrow = "↑" if da > 0 else ("↓" if da < 0 else "•")
                    delta_txt = f"{arrow} {da:+d}（{d['window_min']}分）"
                    if d.get("health_changed"):
                        delta_txt += "  状態変化"
                    st.caption(delta_txt)

                if is_maint:
                    st.caption("Maintenance（最小版：手動フラグ）")
                    st.divider()
                    continue

                meta = f"Alarms: **{r['alarms']}**"
                if r.get("suspected"):
                    meta += f"  ·  Suspected: `{r['suspected']}`"
                st.caption(meta)
                st.divider()

            if len(items) > max_show:
                st.caption(f"…他 {len(items) - max_show} 件（表示は上位 {max_show} 件）")

    _render_bucket(col_map["停止"], "停止")
    _render_bucket(col_map["劣化"], "劣化")
    _render_bucket(col_map["要注意"], "要注意")
    _render_bucket(col_map["正常"], "正常")

    with st.expander("🛠️ Maintenance（最小版：手動フラグ）", expanded=False):
        st.caption("将来は計画停止情報の外部連携に置換予定。いまは手動でグレーアウト対象（会社）を指定します。")
        ts = list_tenants()
        selected = st.multiselect(
            "Maintenance 中の会社",
            options=ts,
            default=[t for t in ts if maint.get(t, False)],
            format_func=lambda x: display_company(x),
        )
        st.session_state.maint_flags = {t: (t in selected) for t in ts}


# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.markdown("### ⚡ Scenario Controller")
selected_scenario = st.sidebar.radio(
    "発生シナリオ",
    ["正常稼働", "WAN全回線断", "FW片系障害", "L2SWサイレント障害"],
)

tenants = list_tenants()
tenant_id = st.sidebar.selectbox(
    "テナント（会社）",
    tenants,
    index=0,
    format_func=lambda x: display_company(x),
)

networks = list_networks(tenant_id)
network_id = st.sidebar.selectbox("ネットワーク", networks, index=0)

# -----------------------------
# Top: All Companies Status Board
# -----------------------------
all_rows = _collect_all_scopes(selected_scenario)
_render_status_board(all_rows)

st.markdown("---")

# =============================================================================
# Below: Existing "AIOps インシデント・コックピット"
# =============================================================================
st.header("🛡️ AIOps インシデント・コックピット")
st.info("ここから下は、元の app.py のコックピット描画ブロックをそのまま貼り付けてください（表・トポロジ・AI Analyst Report 等）。")
