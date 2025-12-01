"""
Google Antigravity AIOps Agent - ロジックモジュール
根本原因分析のための因果推論エンジン。
"""

from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from data import TOPOLOGY, NetworkNode

@dataclass
class Alarm:
    device_id: str
    message: str
    severity: str # CRITICAL, WARNING, INFO

@dataclass
class InferenceResult:
    root_cause_node: Optional[NetworkNode]
    root_cause_reason: str
    sop_key: str
    related_alarms: List[Alarm]

class CausalInferenceEngine:
    def __init__(self, topology: Dict[str, NetworkNode]):
        self.topology = topology

    def analyze_alarms(self, alarms: List[Alarm]) -> InferenceResult:
        """
        アラームリストを分析し、根本原因を特定します。
        階層ルール、冗長性ルール、サイレント障害推論を適用します。
        """
        alarmed_device_ids = {a.device_id for a in alarms}
        
        # 1. 階層ルール (Hierarchy Rule): アラームが発生している最上位レイヤーのデバイスを見つける
        # レイヤー順（昇順）にアラームをソート
        sorted_alarms = sorted(
            alarms, 
            key=lambda a: self.topology[a.device_id].layer if a.device_id in self.topology else 999
        )
        
        if not sorted_alarms:
            return InferenceResult(None, "アラームがありません。", "DEFAULT", [])

        top_alarm = sorted_alarms[0]
        top_node = self.topology.get(top_alarm.device_id)
        
        if not top_node:
             return InferenceResult(None, "不明なデバイス", "DEFAULT", alarms)

        # 2. 冗長性ルール (Redundancy Rule): HAペアかどうかをチェック
        if top_node.redundancy_group:
            return self._analyze_redundancy(top_node, alarmed_device_ids, alarms)

        # 3. サイレント障害推論 (Silent Failure Inference)
        # 最上位アラームのデバイスに親がいる場合、その親がサイレント障害を起こしていないかチェック
        if top_node.parent_id:
            silent_failure_result = self._check_silent_failure_for_parent(top_node.parent_id, alarmed_device_ids)
            if silent_failure_result:
                return silent_failure_result

        # デフォルト: 階層ルールの結果
        return InferenceResult(
            root_cause_node=top_node,
            root_cause_reason=f"階層ルール: 最上位レイヤーのデバイス {top_node.id} がダウンしています。",
            sop_key="WAN_FAILURE" if top_node.layer == 1 else "DEFAULT", # 簡易マッピング
            related_alarms=alarms
        )

    def _analyze_redundancy(self, node: NetworkNode, alarmed_ids: Set[str], alarms: List[Alarm]) -> InferenceResult:
        """
        HAペアのロジックを処理します。
        """
        group_members = [n for n in self.topology.values() if n.redundancy_group == node.redundancy_group]
        down_members = [n for n in group_members if n.id in alarmed_ids]
        
        if len(down_members) == len(group_members):
            # 全メンバーダウン -> Critical
            return InferenceResult(
                root_cause_node=node, # 代表ノード
                root_cause_reason=f"冗長性ルール: HAグループ {node.redundancy_group} の全メンバーがダウンしています。",
                sop_key="DEFAULT", # クリティカルなSOPへ誘導すべき
                related_alarms=alarms
            )
        else:
            # 部分障害 -> Warning
            return InferenceResult(
                root_cause_node=node,
                root_cause_reason=f"冗長性ルール: HAグループ {node.redundancy_group} で単一ノード障害が発生しました。フェイルオーバーが有効です。",
                sop_key="FW_HA_WARNING",
                related_alarms=alarms
            )

    def _check_silent_failure_for_parent(self, parent_id: str, alarmed_ids: Set[str]) -> Optional[InferenceResult]:
        """
        特定の親がサイレント障害の根本原因かどうかをチェックします。
        """
        parent_node = self.topology.get(parent_id)
        if not parent_node:
            return None
            
        children = [n for n in self.topology.values() if n.parent_id == parent_id]
        
        # 全ての子デバイスがダウンしているかチェック
        children_down_count = sum(1 for child in children if child.id in alarmed_ids)
        
        if len(children) > 0 and children_down_count == len(children):
             return InferenceResult(
                root_cause_node=parent_node,
                root_cause_reason=f"サイレント障害推論: 親デバイス {parent_id} は沈黙していますが、配下の子デバイスが全滅しています。",
                sop_key="L2_SILENT_FAILURE",
                related_alarms=[] 
            )
        return None

    def _check_silent_failure(self, alarmed_ids: Set[str]) -> InferenceResult:
        """
        互換性のためのヘルパー（現在は使用されていませんが念のため残置）
        """
        return InferenceResult(None, "明確な根本原因が見つかりません。", "DEFAULT", [])
