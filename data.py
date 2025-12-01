"""
Google Antigravity AIOps Agent - データモジュール
ネットワーク構成（トポロジー）のメタデータと標準作業手順書（SOP）を含みます。
"""

from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class NetworkNode:
    id: str
    layer: int
    type: str
    parent_id: Optional[str] = None
    redundancy_group: Optional[str] = None

# Antigravity ネットワークトポロジー
# 構成: WAN(L1) -> FW(L2) -> CoreSW(L3) -> L2SW(L4) -> AP(L5)
TOPOLOGY: Dict[str, NetworkNode] = {
    "WAN_ROUTER_01": NetworkNode("WAN_ROUTER_01", 1, "ROUTER"),
    
    "FW_01_PRIMARY": NetworkNode("FW_01_PRIMARY", 2, "FIREWALL", "WAN_ROUTER_01", "FW_HA_GROUP"),
    "FW_01_SECONDARY": NetworkNode("FW_01_SECONDARY", 2, "FIREWALL", "WAN_ROUTER_01", "FW_HA_GROUP"),
    
    "CORE_SW_01": NetworkNode("CORE_SW_01", 3, "SWITCH", "FW_01_PRIMARY"), # ロジック簡略化のため親をPrimaryに設定
    
    "L2_SW_01": NetworkNode("L2_SW_01", 4, "SWITCH", "CORE_SW_01"),
    "L2_SW_02": NetworkNode("L2_SW_02", 4, "SWITCH", "CORE_SW_01"),
    
    "AP_01": NetworkNode("AP_01", 5, "ACCESS_POINT", "L2_SW_01"),
    "AP_02": NetworkNode("AP_02", 5, "ACCESS_POINT", "L2_SW_01"),
    "AP_03": NetworkNode("AP_03", 5, "ACCESS_POINT", "L2_SW_02"),
    "AP_04": NetworkNode("AP_04", 5, "ACCESS_POINT", "L2_SW_02"),
}

# 標準作業手順書 (SOPs)
# 根本原因IDまたは障害タイプにマッピング
SOPS = {
    "WAN_FAILURE": """
    ### 🚀 Antigravity プロトコル: WAN 復旧
    **重要度**: CRITICAL (緊急)
    **アクションアイテム**:
    1. [キャリアポータル] で回線ステータスを確認してください。
    2. WAN_ROUTER_01 の物理インターフェースの状態を確認してください。
    3. インターフェースがUPの場合、ISPゲートウェイへのPing疎通を確認してください。
    4. 疎通不可の場合、直ちにISPサポートへ連絡してください (チケット優先度: P1)。
    """,
    
    "FW_HA_WARNING": """
    ### ⚠️ Antigravity プロトコル: FW 冗長性チェック
    **重要度**: WARNING (警告)
    **アクションアイテム**:
    1. アクティブノードへのトラフィックフェイルオーバーが正常か確認してください。
    2. FW_01_PRIMARY と FW_01_SECONDARY 間の同期ステータスを確認してください。
    3. 障害ノードのログを確認し、ハードウェアまたはソフトウェアクラッシュの痕跡を探してください。
    4. 復旧のためのメンテナンスウィンドウをスケジュールしてください。
    """,
    
    "L2_SILENT_FAILURE": """
    ### 👻 Antigravity プロトコル: サイレント障害検知
    **重要度**: HIGH (高)
    **アクションアイテム**:
    1. **推定根本原因**: アラームは出ていませんが、上位の L2スイッチ がダウンしている可能性があります。
    2. 疑わしい L2スイッチ の電源状態とアップリンク接続を確認してください。
    3. 管理プレーンが応答しない場合は、デバイスを再起動してください。
    4. リモート復旧に失敗した場合は、フィールドエンジニアを派遣してください。
    """,
    
    "DEFAULT": """
    ### 🔍 Antigravity プロトコル: 一般調査
    **重要度**: UNKNOWN (不明)
    **アクションアイテム**:
    1. デバイスログを確認してください。
    2. 接続性を確認してください。
    3. ネットワークオペレーションセンター (NOC) へエスカレーションしてください。
    """
}
