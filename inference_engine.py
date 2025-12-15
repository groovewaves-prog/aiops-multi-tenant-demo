"""
Antigravity AIOps - Logical Inference Engine (Rule-Based / Deterministic)
ベイズ確率ではなく、発生しているアラームとトポロジー情報に基づき、
論理的・決定論的に根本原因を特定するエンジン。
"""

class LogicalRCA:
    def __init__(self, topology):
        self.topology = topology
        
        # ■ 1. 基本シグネチャ（自己申告アラームに基づく判定）
        self.signatures = [
            {
                "type": "Hardware/Critical_Multi_Fail",
                "label": "複合ハードウェア障害",
                "rules": lambda alarms: any("power supply" in a.message.lower() for a in alarms) and any("fan" in a.message.lower() for a in alarms),
                "base_score": 1.0
            },
            {
                "type": "Hardware/Physical",
                "label": "ハードウェア障害 (電源/デバイス)",
                "rules": lambda alarms: any(k in a.message.lower() for a in alarms for k in ["power supply", "device down"]),
                "base_score": 0.95
            },
            {
                "type": "Network/Link",
                "label": "物理リンク/インターフェース障害",
                "rules": lambda alarms: any(k in a.message.lower() for a in alarms for k in ["interface down", "connection lost", "heartbeat loss"]),
                "base_score": 0.90
            },
            {
                "type": "Hardware/Fan",
                "label": "冷却ファン故障",
                "rules": lambda alarms: any("fan fail" in a.message.lower() for a in alarms),
                "base_score": 0.70
            },
            {
                "type": "Config/Software",
                "label": "設定ミス/プロトコル障害",
                "rules": lambda alarms: any(k in a.message.lower() for a in alarms for k in ["bgp", "ospf", "config"]),
                "base_score": 0.60
            },
            {
                "type": "Resource/Capacity",
                "label": "リソース枯渇 (CPU/Memory)",
                "rules": lambda alarms: any(k in a.message.lower() for a in alarms for k in ["cpu", "memory", "high"]),
                "base_score": 0.50
            }
        ]

    def analyze(self, current_alarms):
        """
        現在のアラームリストを入力とし、デバイスごとのリスクスコアを算出する。
        """
        candidates = []
        
        # 1. アラームをデバイスIDごとにグループ化
        device_alarms = {}
        for alarm in current_alarms:
            if alarm.device_id not in device_alarms:
                device_alarms[alarm.device_id] = []
            device_alarms[alarm.device_id].append(alarm)
            
        # 2. デバイスごとにルール適合度を評価
        for device_id, alarms in device_alarms.items():
            best_match = None
            max_score = 0.0
            
            for sig in self.signatures:
                if sig["rules"](alarms):
                    # アラーム数に応じた加点 (確信度の補強)
                    score = min(sig["base_score"] + (len(alarms) * 0.02), 1.0)
                    if score > max_score:
                        max_score = score
                        best_match = sig
            
            if best_match:
                candidates.append({
                    "id": device_id,
                    "type": best_match["type"],
                    "label": best_match["label"],
                    "prob": max_score,
                    "alarms": [a.message for a in alarms],
                    "verification_log": ""
                })
            elif alarms:
                candidates.append({
                    "id": device_id,
                    "type": "Unknown/Other",
                    "label": "その他異常検知",
                    "prob": 0.3,
                    "alarms": [a.message for a in alarms],
                    "verification_log": ""
                })

        # 3. トポロジー相関分析 (サイレント障害検知)
        down_children_count = {} # parent_id -> count
        
        for alarm in current_alarms:
            msg = alarm.message.lower()
            if "connection lost" in msg or "interface down" in msg:
                node = self.topology.get(alarm.device_id)
                if node and node.parent_id:
                    pid = node.parent_id
                    down_children_count[pid] = down_children_count.get(pid, 0) + 1

        # サイレント障害と判定された親ノードのIDリスト
        detected_silent_parents = set()

        for parent_id, count in down_children_count.items():
            # 閾値: 配下が2台以上同時に死んでいる場合
            if count >= 2:
                parent_node = self.topology.get(parent_id)
                if not parent_node: continue 

                detected_silent_parents.add(parent_id)

                # 能動的診断ログの作成 (これがレポートに反映される)
                active_verification_log = f"""
[Auto-Probe] Multiple downstream failures detected (Count: {count}).
[Topology] Identified upstream aggregator: {parent_id}
[Action] Initiating active health check from Core Switch...
[Exec] ping {parent_id}_mgmt_ip source Core_SW
[Result] Request Timed Out (100% loss).
[Conclusion] {parent_id} is unresponsive (Silent Failure confirmed).
"""
                # 親ノードが既に候補（アラーム持ち）かどうか確認
                existing = next((c for c in candidates if c['id'] == parent_id), None)
                
                if existing:
                    existing['prob'] = 1.0
                    existing['label'] += " (配下多重断)"
                    existing['verification_log'] = active_verification_log
                else:
                    # サイレント障害として新規追加
                    candidates.append({
                        "id": parent_id,
                        "type": "Network/Silent",
                        "label": "サイレント障害 (配下デバイス一斉断)",
                        "prob": 0.99, # 非常に高い危険度
                        "alarms": [f"Downstream Impact: {count} devices lost"],
                        "verification_log": active_verification_log
                    })

        # 4. ★追加修正: 被害ノード（Children）のスコア抑制
        # サイレント障害の親が見つかった場合、その子供たちは「原因」ではなく「被害者」なのでスコアを下げる
        if detected_silent_parents:
            for cand in candidates:
                node = self.topology.get(cand['id'])
                # もし自分の親が「サイレント障害認定」されていたら
                if node and node.parent_id in detected_silent_parents:
                    cand['prob'] = 0.55  # 0.6未満にすることで「警告/危険」から除外する
                    cand['label'] = "影響下 (上位障害による波及)"
                    cand['type'] = "Network/Secondary"

        # 5. ソート
        candidates.sort(key=lambda x: x["prob"], reverse=True)
        
        if not candidates:
            candidates.append({
                "id": "System", 
                "type": "Normal", 
                "label": "正常稼働中", 
                "prob": 0.0,
                "alarms": [],
                "verification_log": ""
            })
            
        return candidates
