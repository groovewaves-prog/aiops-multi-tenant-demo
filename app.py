import streamlit as st
import graphviz
import os
import time
import google.generativeai as genai
import json
import pandas as pd  # ★修正: ここに移動しました
from google.api_core import exceptions as google_exceptions

# モジュール群のインポート
from data import TOPOLOGY
from logic import CausalInferenceEngine, Alarm, simulate_cascade_failure
from network_ops import run_diagnostic_simulation, generate_remediation_commands, predict_initial_symptoms, generate_fake_log_by_ai
from verifier import verify_log_content, format_verification_report
# from dashboard import render_intelligent_alarm_viewer # app.py内に実装したためコメントアウト可
from inference_engine import LogicalRCA

# --- ページ設定 ---
st.set_page_config(page_title="Antigravity Autonomous", page_icon="⚡", layout="wide")

# ==========================================
# 関数定義
# ==========================================
def find_target_node_id(topology, node_type=None, layer=None, keyword=None):
    """トポロジーから条件に合うノードIDを検索"""
    for node_id, node in topology.items():
        if node_type and node.type != node_type: continue
        if layer and node.layer != layer: continue
        if keyword:
            hit = False
            if keyword in node_id: hit = True
            for v in node.metadata.values():
                if isinstance(v, str) and keyword in v: hit = True
            if not hit: continue
        return node_id
    return None

def load_config_by_id(device_id):
    """configsフォルダから設定ファイルを読み込む"""
    possible_paths = [f"configs/{device_id}.txt", f"{device_id}.txt"]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
    return "Config file not found."

def generate_content_with_retry(model, prompt, stream=True, retries=3):
    """503エラー対策のリトライ付き生成関数"""
    for i in range(retries):
        try:
            return model.generate_content(prompt, stream=stream)
        except google_exceptions.ServiceUnavailable:
            if i == retries - 1: raise
            time.sleep(2 * (i + 1))
    return None

def render_topology(alarms, root_cause_candidates):
    """トポロジー図の描画 (AI判定結果を反映)"""
    graph = graphviz.Digraph()
    graph.attr(rankdir='TB')
    graph.attr('node', shape='box', style='rounded,filled', fontname='Helvetica')
    
    alarm_map = {a.device_id: a for a in alarms}
    alarmed_ids = set(alarm_map.keys())
    
    # AIが特定した根本原因IDのセット（スコア0.6以上）
    root_cause_ids = {c['id'] for c in root_cause_candidates if c['prob'] > 0.6}
    
    for node_id, node in TOPOLOGY.items():
        color = "#e8f5e9"
        penwidth = "1"
        fontcolor = "black"
        label = f"{node_id}\n({node.type})"
        
        red_type = node.metadata.get("redundancy_type")
        if red_type: label += f"\n[{red_type} Redundancy]"
        vendor = node.metadata.get("vendor")
        if vendor: label += f"\n[{vendor}]"

        # 色分けロジック
        if node_id in root_cause_ids:
            this_alarm = alarm_map.get(node_id)
            if this_alarm and this_alarm.severity == "WARNING":
                color = "#fff9c4" # Yellow
            else:
                color = "#ffcdd2" # Red
            
            penwidth = "3"
            label += "\n[ROOT CAUSE]"
            
        elif node_id in alarmed_ids:
            color = "#fff9c4" 
        
        graph.node(node_id, label=label, fillcolor=color, color='black', penwidth=penwidth, fontcolor=fontcolor)
    
    for node_id, node in TOPOLOGY.items():
        if node.parent_id:
            graph.edge(node.parent_id, node_id)
            parent_node = TOPOLOGY.get(node.parent_id)
            if parent_node and parent_node.redundancy_group:
                partners = [n.id for n in TOPOLOGY.values() 
                           if n.redundancy_group == parent_node.redundancy_group and n.id != parent_node.id]
                for partner_id in partners:
                    graph.edge(partner_id, node_id)
    return graph

# --- UI構築 ---
st.title("⚡ Antigravity Autonomous Agent")

api_key = None
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    api_key = os.environ.get("GOOGLE_API_KEY")

# --- サイドバー ---
with st.sidebar:
    st.header("⚡ Scenario Controller")
    SCENARIO_MAP = {
        "基本・広域障害": ["正常稼働", "1. WAN全回線断", "2. FW片系障害", "3. L2SWサイレント障害"],
        "WAN Router": ["4. [WAN] 電源障害：片系", "5. [WAN] 電源障害：両系", "6. [WAN] BGPルートフラッピング", "7. [WAN] FAN故障", "8. [WAN] メモリリーク"],
        "Firewall (Juniper)": ["9. [FW] 電源障害：片系", "10. [FW] 電源障害：両系", "11. [FW] FAN故障", "12. [FW] メモリリーク"],
        "L2 Switch": ["13. [L2SW] 電源障害：片系", "14. [L2SW] 電源障害：両系", "15. [L2SW] FAN故障", "16. [L2SW] メモリリーク"],
        "複合・その他": ["17. [WAN] 複合障害：電源＆FAN", "18. [Complex] 同時多発：FW & AP", "99. [Live] Cisco実機診断"]
    }
    selected_category = st.selectbox("対象カテゴリ:", list(SCENARIO_MAP.keys()))
    selected_scenario = st.radio("発生シナリオ:", SCENARIO_MAP[selected_category])
    st.markdown("---")
    if api_key: st.success("API Connected")
    else:
        st.warning("API Key Missing")
        user_key = st.text_input("Google API Key", type="password")
        if user_key: api_key = user_key

# --- セッション管理 ---
if "current_scenario" not in st.session_state:
    st.session_state.current_scenario = "正常稼働"

# 変数初期化
for key in ["live_result", "messages", "chat_session", "trigger_analysis", "verification_result", "generated_report", "verification_log", "last_report_cand_id", "logic_engine"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "messages" and key != "trigger_analysis" else ([] if key == "messages" else False)

# エンジン初期化
if not st.session_state.logic_engine:
    st.session_state.logic_engine = LogicalRCA(TOPOLOGY)

# シナリオ切り替え時のリセット
if st.session_state.current_scenario != selected_scenario:
    st.session_state.current_scenario = selected_scenario
    st.session_state.messages = []      
    st.session_state.chat_session = None 
    st.session_state.live_result = None 
    st.session_state.trigger_analysis = False
    st.session_state.verification_result = None
    st.session_state.generated_report = None
    st.session_state.verification_log = None 
    st.session_state.last_report_cand_id = None
    if "remediation_plan" in st.session_state: del st.session_state.remediation_plan
    st.rerun()

# ==========================================
# メインロジック
# ==========================================
alarms = []
target_device_id = None
root_severity = "CRITICAL"
is_live_mode = False

# 1. アラーム生成ロジック
if "Live" in selected_scenario: is_live_mode = True
elif "WAN全回線断" in selected_scenario:
    target_device_id = find_target_node_id(TOPOLOGY, node_type="ROUTER")
    if target_device_id: alarms = simulate_cascade_failure(target_device_id, TOPOLOGY)
elif "FW片系障害" in selected_scenario:
    target_device_id = find_target_node_id(TOPOLOGY, node_type="FIREWALL")
    if target_device_id:
        alarms = [Alarm(target_device_id, "Heartbeat Loss", "WARNING")]
        root_severity = "WARNING"

elif "L2SWサイレント障害" in selected_scenario:
    target_device_id = "L2_SW_01"
    if target_device_id not in TOPOLOGY:
        target_device_id = find_target_node_id(TOPOLOGY, keyword="L2_SW")
    if target_device_id and target_device_id in TOPOLOGY:
        child_nodes = [nid for nid, n in TOPOLOGY.items() if n.parent_id == target_device_id]
        alarms = [Alarm(child, "Connection Lost", "CRITICAL") for child in child_nodes]
    else:
        st.error("Error: L2 Switch definition not found")

elif "複合障害" in selected_scenario:
    target_device_id = find_target_node_id(TOPOLOGY, node_type="ROUTER")
    if target_device_id:
        alarms = [
            Alarm(target_device_
