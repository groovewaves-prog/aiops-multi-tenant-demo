import streamlit as st
import graphviz
import os
import google.generativeai as genai

# データ・ロジック・運用モジュールのインポート
from data import TOPOLOGY
from logic import CausalInferenceEngine, Alarm, simulate_cascade_failure
from network_ops import run_diagnostic_simulation

# --- ページ設定 ---
st.set_page_config(page_title="Antigravity Live", page_icon="⚡", layout="wide")

# --- 関数: トポロジー図の生成 ---
def render_topology(alarms, root_cause_node):
    graph = graphviz.Digraph()
    graph.attr(rankdir='TB')
    graph.attr('node', shape='box', style='rounded,filled', fontname='Helvetica')
    
    alarmed_ids = {a.device_id for a in alarms}
    
    for node_id, node in TOPOLOGY.items():
        color = "#e8f5e9" # Default Green
        penwidth = "1"
        fontcolor = "black"
        label = f"{node_id}\n({node.type})"
        
        if root_cause_node and node_id == root_cause_node.id:
            color = "#ffcdd2" # Root Cause Red
            penwidth = "3"
            label += "\n[ROOT CAUSE]"
        elif node_id in alarmed_ids:
            color = "#fff9c4" # Alarm Yellow
        
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

# --- 関数: Config自動読み込み ---
def load_config_by_id(device_id):
    path = f"configs/{device_id}.txt"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None

# --- UI構築 ---
st.title("⚡ Antigravity AI Agent (Live Demo)")

# APIキー取得
api_key = None
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    api_key = os.environ.get("GOOGLE_API_KEY")

# サイドバー
with st.sidebar:
    st.header("⚡ 運用モード選択")
    selected_scenario = st.radio(
        "シナリオ:", 
        ("正常稼働", "1. WAN全回線断", "2. FW片系障害", "3. L2SWサイレント障害", "4. [Live] Cisco実機診断")
    )
    
    st.markdown("---")
    if api_key:
        st.success("API Connected")
    else:
        st.warning("API Key Missing")
        user_key = st.text_input("Google API Key", type="password")
        if user_key: api_key = user_key

# セッション状態管理
if "current_scenario" not in st.session_state:
    st.session_state.current_scenario = "正常稼働"
    st.session_state.messages = []
    st.session_state.chat_session = None 
    st.session_state.live_result = None
    st.session_state.trigger_analysis = False # 診断後の分析トリガー

# シナリオ変更時のリセット処理
if st.session_state.current_scenario != selected_scenario:
    st.session_state.current_scenario = selected_scenario
    st.session_state.messages = []
    st.session_state.chat_session = None
    st.session_state.live_result = None
    st.session_state.trigger_analysis = False
    st.rerun()

# --- アラーム生成ロジック ---
alarms = []
if selected_scenario == "1. WAN全回線断":
    alarms = simulate_cascade_failure("WAN_ROUTER_01", TOPOLOGY)
elif selected_scenario == "2. FW片系障害":
    alarms = [Alarm("FW_01_PRIMARY", "Heartbeat Loss", "WARNING")]
elif selected_scenario == "3. L2SWサイレント障害":
    alarms = [Alarm("AP_01", "Connection Lost", "CRITICAL"), Alarm("AP_02", "Connection Lost", "CRITICAL")]

# 推論実行
root_cause = None
inference_result = None
reason = ""

if alarms:
    engine = CausalInferenceEngine(TOPOLOGY)
    inference_result = engine.analyze_alarms(alarms)
    root_cause = inference_result.root_cause_node
    reason = inference_result.root_cause_reason

# --- メイン画面レイアウト ---
col1, col2 = st.columns([1, 1])

# 左カラム：トポロジー ＆ 自律調査UI
with col1:
    st.subheader("Network Status")
    st.graphviz_chart(render_topology(alarms, root_cause), use_container_width=True)
    
    if root_cause:
        st.markdown(
            f'<div style="color: #d32f2f; font-weight: bold; font-size: 15px; background-color: #fdecea; padding: 10px; border-radius: 5px;">'
            f'🚨 緊急アラート：{root_cause.id} ダウン'
            f'</div>', 
            unsafe_allow_html=True
        )
        st.caption(f"理由: {reason}")
    
    is_live_mode = (selected_scenario == "4. [Live] Cisco実機診断")
    
    if is_live_mode or root_cause:
        st.markdown("---")
        st.info("🛠 **自律調査エージェント**")
        
        # ボタン: 診断実行
        if st.button("🚀 診断実行 (Simulation)", type="primary"):
            if not api_key:
                st.error("API Key Required")
            else:
                with st.status("Agent Operating...", expanded=True) as status:
                    st.write("🔌 Initiating connection simulation...")
                    res = run_diagnostic_simulation(selected_scenario)
                    st.session_state.live_result = res
                    
                    if res["status"] == "SUCCESS":
                        st.write("✅ Data retrieved.")
                        status.update(label="Complete!", state="complete", expanded=False)
                    else:
                        st.write("❌ Connection Failed (As expected).")
                        status.update(label="Target Unreachable", state="error", expanded=False)
                    
                    # 【重要修正】チャットをリセットせず、次の分析トリガーだけONにする
                    st.session_state.trigger_analysis = True
                    st.rerun()

        # 診断結果表示
        if st.session_state.live_result:
            res = st.session_state.live_result
            if res["status"] == "SUCCESS":
                st.success("🛡️ **Data Sanitized**: パスワード・IPアドレスをマスク処理しました。")
                with st.expander("📄 取得ログ (Sanitized View)", expanded=True):
                    st.code(res["sanitized_log"], language="text")
            else:
                st.error(f"診断結果: {res['error']}")
                st.caption("※エージェントはこの接続エラー自体を『診断情報』として利用します。")

# 右カラム：AIチャット
with col2:
    st.subheader("AI Analyst Report")

    if not api_key:
        st.error("APIキーを設定してください")
        st.stop()

    # Gemini初期設定 (まだセッションがない場合のみ)
    if st.session_state.chat_session is None and selected_scenario != "正常稼働":
        genai.configure(api_key=api_key)
        generation_config = {"temperature": 0.0, "max_output_tokens": 1500}
        model = genai.GenerativeModel("gemini-2.0-flash", generation_config=generation_config)
        
        # --- 初期分析プロンプト (トポロジー視点) ---
        system_prompt = ""
        if root_cause:
            config_content = load_config_by_id(root_cause.id)
            system_prompt = f"""
            あなたはAIOpsエージェントです。以下の障害について初期報告してください。
            根本原因: {root_cause.id} ({root_cause.type})
            理由: {reason}
            """
            if config_content:
                system_prompt += f"\n【Configあり】\n{config_content}\n上記設定に基づき、疑わしい箇所を指摘してください。"
            else:
                system_prompt += "\n【Configなし】\n一般的な復旧手順を提示してください。"
            
            system_prompt += "\nフォーマット: 緊急度(絵文字)、状況要約、推奨アクション(調査など)の順。"

        if system_prompt:
            history = [{"role": "user", "parts": [system_prompt]}]
            chat = model.start_chat(history=history)
            try:
                with st.spinner("Initial Analysis..."):
                    response = chat.send_message("状況報告をお願いします。")
                    st.session_state.chat_session = chat
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Error: {e}")

    # --- 診断実行後の追加分析 (トリガーがONの時) ---
    if st.session_state.trigger_analysis and st.session_state.chat_session:
        live_data = st.session_state.live_result
        log_content = live_data.get('sanitized_log') or f"接続エラー: {live_data.get('error')}"
        
        # 追記用プロンプト
        follow_up_prompt = f"""
        自律調査エージェントが診断コマンドを実行しました。
        以下の実行結果に基づき、詳細な『ネクストアクション実行レポート』を作成してください。

        【診断入力データ】
        ステータス: {live_data['status']}
        詳細情報: {log_content}

        【出力要件】
        以下のフォーマットで出力すること。
        
        ### 🛠 ネクストアクション実行レポート
        
        **1. データ保全と接続確認:**
        接続試行およびログ取得を実施。
        → **結果: {live_data['status']}** (🛡️ 機密情報はフィルタリング済み)
        
        **2. 詳細分析:**
        [接続エラーの場合は『疎通不可のため確認できません』と記述。ログがある場合は内容を分析]
        → [分析結果]
        
        **3. 物理/インターフェース確認:**
        [接続エラーの場合は『電源断や物理障害の可能性大』と推論]
        → [分析結果]
        
        ---
        **最終判定:** [結論]
        """
        
        # ユーザーメッセージとして履歴に追加
        st.session_state.messages.append({"role": "user", "content": "診断を実行しました。結果を分析してください。"})
        
        with st.spinner("Analyzing Diagnostic Data..."):
            try:
                response = st.session_state.chat_session.send_message(follow_up_prompt)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Error: {e}")
        
        # トリガーをOFFに戻す
        st.session_state.trigger_analysis = False
        st.rerun()

    # --- チャットUI表示 (スクロールコンテナ) ---
    chat_container = st.container(height=600)
    
    with chat_container:
        for message in st.session_state.messages:
            # 内部的なプロンプトは見せず、ユーザーの会話として自然なものを表示
            if "以下の診断結果に基づき" in message["content"]:
                continue # プロンプト自体は非表示にするフィルタ
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # 入力欄
    if prompt := st.chat_input("AIエージェントに指示..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        if st.session_state.chat_session:
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        try:
                            res = st.session_state.chat_session.send_message(prompt)
                            st.markdown(res.text)
                            st.session_state.messages.append({"role": "assistant", "content": res.text})
                        except Exception as e:
                            st.error(f"Error: {e}")
