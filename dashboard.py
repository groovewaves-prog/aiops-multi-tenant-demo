import streamlit as st
import pandas as pd

def render_intelligent_alarm_viewer(bayes_engine, selected_scenario):
    """
    AIOps時代のインシデント管理ビューアー（インタラクティブ版）
    行をクリックすると詳細を選択可能
    """
    st.markdown("### 🛡️ AIOps インシデント・コックピット")
    
    # 1. KPIメトリクス
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="📉 ノイズ削減率", value="98.5%", delta="高効率稼働中")
    with col2:
        st.metric(label="📨 処理したアラーム総数", value="154件", delta="-153件 (抑制済)", delta_color="inverse")
    with col3:
        st.metric(label="🚨 要対応インシデント", value="1件", delta="対処が必要")

    st.markdown("---")
    
    # 2. ランキング取得
    ranking = bayes_engine.get_ranking()
    
    # 3. データ整形
    data = []
    for rank, candidate in enumerate(ranking[:4], 1): 
        prob = candidate["prob"]
        
        if prob > 0.8:
            status = "🔴 危険 (根本原因)"
            action = "🚀 自動修復が可能"
            impact = "大"
            raw_status = "CRITICAL"
        elif prob > 0.4:
            status = "🟡 警告 (被疑箇所)"
            action = "🔍 詳細調査を推奨"
            impact = "中"
            raw_status = "WARNING"
        else:
            status = "⚪ 監視中"
            action = "👁️ 静観"
            impact = "小"
            raw_status = "INFO"

        data.append({
            "順位": rank,
            "ID": candidate['id'], # 隠しカラム（参照用）
            "AI診断": status,
            "根本原因分析": f"デバイス: {candidate['id']}\n原因種別: {candidate['type']}",
            "確信度": prob,
            "影響範囲": impact,
            "推奨アクション": action,
            "RawStatus": raw_status,
            "Type": candidate['type'],
            "ProbVal": prob
        })

    df = pd.DataFrame(data)

    # 4. インタラクティブなDataFrame表示
    # on_select="rerun" により、クリック時にアプリが再実行され、選択状態が反映される
    event = st.dataframe(
        df,
        column_order=["順位", "AI診断", "根本原因分析", "確信度", "影響範囲", "推奨アクション"],
        column_config={
            "順位": st.column_config.NumberColumn("#", format="%d", width="small"),
            "AI診断": st.column_config.TextColumn("ステータス", width="medium"),
            "根本原因分析": st.column_config.TextColumn("📌 根本原因候補", width="large"),
            "確信度": st.column_config.ProgressColumn("AI確信度", format="%.1f", min_value=0, max_value=1),
            "推奨アクション": st.column_config.TextColumn("🤖 Next Action"),
            "影響範囲": st.column_config.TextColumn("影響度", width="small"),
        },
        use_container_width=True,
        hide_index=True,
        height=250,
        on_select="rerun",          # ★追加: 選択イベントを有効化
        selection_mode="single-row" # ★追加: 単一行選択
    )
    
    # 選択された行の候補データを特定して返す
    selected_candidate = None
    
    if len(event.selection.rows) > 0:
        # ユーザーがクリックした行
        idx = event.selection.rows[0]
        selected_row = df.iloc[idx]
        # rankingリストから該当する辞書を探す
        target_id = selected_row["ID"]
        target_type = selected_row["Type"]
        for cand in ranking:
            if cand['id'] == target_id and cand['type'] == target_type:
                selected_candidate = cand
                break
    else:
        # 選択なしの場合はトップ（1位）をデフォルトとする
        selected_candidate = ranking[0]
        
    return selected_candidate
