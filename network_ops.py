"""
Google Antigravity AIOps Agent - Network Operations Module (Optimized)
"""
import re
import os
import time
import logging
import google.generativeai as genai
from netmiko import ConnectHandler
from typing import Optional

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =====================================================
# デバイス設定（デモ用）
# =====================================================
SANDBOX_DEVICE = {
    'device_type': 'cisco_nxos',
    'host': 'sandbox-nxos-1.cisco.com',
    'username': 'admin',
    'password': 'Admin_1234!',
    'port': 22,
    'global_delay_factor': 2,
    'banner_timeout': 30,
    'conn_timeout': 30,
}

# =====================================================
# 拡張版セキュリティマスキング
# =====================================================
def sanitize_output(text: str) -> str:
    rules = [
        (r'(password|secret)\s+\d+\s+\S+', r'\1 <HIDDEN_PASSWORD>', re.IGNORECASE),
        (r'(encrypted password)\s+\S+', r'\1 <HIDDEN_PASSWORD>', re.IGNORECASE),
        (r'(username \S+ privilege \d+ secret \d+)\s+\S+', r'\1 <HIDDEN_SECRET>', re.IGNORECASE),
        (r'(snmp-server community)\s+\S+', r'\1 <HIDDEN_COMMUNITY>', re.IGNORECASE),
        (r'(api[_-]?key|token|bearer)\s*[:=]\s*[\w\-\.]+', r'\1=<MASKED_TOKEN>', re.IGNORECASE),
        (r'(authorization:\s*bearer)\s+[\w\-\.]+', r'\1 <MASKED_TOKEN>', re.IGNORECASE),
        (r'(x-api-key:\s*)[\w\-\.]+', r'\1<MASKED_TOKEN>', re.IGNORECASE),
        (r'(serial\s*(?:number)?|sn)\s*[:=]\s*[\w\-]+', r'\1=<MASKED_SERIAL>', re.IGNORECASE),
        # IPv4 Public IP Masking (Private IPs 10./172./192. are preserved)
        (r'\b(?!(?:10|127|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.)(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b', '<MASKED_PUBLIC_IP>', 0),
        # IPv6 Masking
        (r'(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}', '<MASKED_IPV6>', 0),
        (r'::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}', '<MASKED_IPV6>', 0),
        # MAC Address
        (r'([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}', '<MASKED_MAC>', 0),
        (r'([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}', '<MASKED_MAC>', 0),
    ]
    
    for pattern, replacement, flags in rules:
        text = re.sub(pattern, replacement, text, flags=flags)
    
    return text

# =====================================================
# AIモデルマネージャー（シングルトン）
# =====================================================
class AIModelManager:
    _instance = None
    _model = None
    _api_key = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_model(self, api_key: str, model_name: str = "gemma-3-12b-it"):
        if not api_key:
            raise ValueError("API Key is required")
        
        if self._model is None or self._api_key != api_key:
            try:
                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel(
                    model_name,
                    generation_config={"temperature": 0.0}
                )
                self._api_key = api_key
            except Exception as e:
                logger.error(f"Failed to initialize AI model: {e}")
                raise
        return self._model

_ai_manager = AIModelManager()

# =====================================================
# シナリオ定義ヘルパー
# =====================================================
def _get_status_instructions(scenario_name: str) -> str:
    if "電源" in scenario_name and "片系" in scenario_name:
        return """
【状態定義: 電源冗長稼働中 (片系ダウン)】
1. ハードウェアステータス: Power Supply 1: **Faulty / Failed**, Power Supply 2: **OK**
2. サービス影響: なし (インターフェース UP, Ping 成功)
3. エラーログ: 電源障害を示すSyslogまたはTrapを含めること。
"""
    elif "電源" in scenario_name and "両系" in scenario_name:
        return """
【状態定義: 全電源喪失】
1. ログ: "Connection Refused" または再起動直後のブートログのみ。
"""
    elif "FAN" in scenario_name:
        return """
【状態定義: ファン故障】
1. ハードウェアステータス: Fan Tray 1 **Failure**
2. 温度: 上昇中だが閾値内 (Warning)
3. サービス影響: なし
"""
    elif "メモリ" in scenario_name:
        return """
【状態定義: メモリリーク】
1. メモリ使用率: **98%以上**
2. プロセス: 特定のプロセス（例: SSHD, FlowMonitor等）が異常消費している様子を明確に示すこと。
3. Syslog: メモリ割り当て失敗 (Malloc Fail) を含めること。
"""
    elif "BGP" in scenario_name:
        return """
【状態定義: BGPフラッピング】
1. BGP状態: 特定のNeighborが Idle / Active を繰り返している。
2. 物理IF: UP/UP
"""
    elif "全回線断" in scenario_name:
        return """
【状態定義: 物理リンクダウン】
1. 主要インターフェース: **DOWN / DOWN** (Carrier Loss)
2. Ping: 100% Loss
"""
    return ""

# =====================================================
# 各種生成関数 (リトライ対応)
# =====================================================
def generate_fake_log_by_ai(scenario_name: str, target_node, api_key: str) -> str:
    try:
        model = _ai_manager.get_model(api_key)
    except Exception as e:
        return f"Error: {str(e)}"
    
    vendor = target_node.metadata.get("vendor", "Unknown Vendor")
    os_type = target_node.metadata.get("os", "Unknown OS")
    hostname = target_node.id
    instructions = _get_status_instructions(scenario_name)
    
    prompt = f"""
    あなたはネットワーク機器のCLIシミュレーターです。
    シナリオ: {scenario_name}
    対象機器: {hostname} ({vendor} {os_type})
    {instructions}
    出力ルール: 解説不要。CLIの生テキストのみ出力。
    """
    
    for attempt in range(3):
        try:
            return model.generate_content(prompt).text
        except Exception as e:
            time.sleep(1)
            if attempt == 2: return f"AI Generation Error: {str(e)}"

def generate_config_from_intent(target_node, current_config, intent_text, api_key):
    try:
        model = _ai_manager.get_model(api_key)
    except Exception as e:
        return f"Error: {str(e)}"
        
    vendor = target_node.metadata.get("vendor", "Unknown")
    os_type = target_node.metadata.get("os", "Unknown")
    
    prompt = f"""
    Config生成。対象: {target_node.id} ({vendor} {os_type})
    現状: {current_config}
    意図: {intent_text}
    出力: 投入コマンドのみ(Markdown)
    """
    
    for attempt in range(3):
        try:
            return model.generate_content(prompt).text
        except Exception as e:
            time.sleep(1)
            if attempt == 2: return f"Config Gen Error: {str(e)}"

def generate_health_check_commands(target_node, api_key):
    try:
        model = _ai_manager.get_model(api_key)
    except Exception as e:
        return f"Error: {str(e)}"
        
    vendor = target_node.metadata.get("vendor", "Unknown")
    os_type = target_node.metadata.get("os", "Unknown")
    
    prompt = f"Netmiko正常性確認コマンドを3つ生成せよ。対象: {vendor} {os_type}。出力: コマンドのみ箇条書き"
    
    for attempt in range(3):
        try:
            return model.generate_content(prompt).text
        except Exception as e:
            time.sleep(1)
            if attempt == 2: return f"Command Gen Error: {str(e)}"

# =====================================================
# 診断実行メイン関数
# =====================================================
def run_diagnostic_simulation(scenario_type: str, target_node=None, api_key: str = None) -> dict:
    time.sleep(1.5)
    
    if "---" in scenario_type or "正常" in scenario_type:
        return {"status": "SKIPPED", "sanitized_log": "No action required.", "error": None}

    if "[Live]" in scenario_type:
        commands = ["terminal length 0", "show version", "show interface brief", "show ip route"]
        try:
            with ConnectHandler(**SANDBOX_DEVICE) as ssh:
                if not ssh.check_enable_mode(): ssh.enable()
                prompt = ssh.find_prompt()
                raw_output = f"Connected to: {prompt}\n"
                for cmd in commands:
                    output = ssh.send_command(cmd)
                    raw_output += f"\n{'='*30}\n[Command] {cmd}\n{output}\n"
        except Exception as e:
            return {"status": "ERROR", "sanitized_log": "", "error": str(e)}
        return {"status": "SUCCESS", "sanitized_log": sanitize_output(raw_output), "error": None}
            
    elif any(x in scenario_type for x in ["全回線断", "サイレント", "両系"]):
        return {"status": "ERROR", "sanitized_log": "", "error": "Connection timed out"}

    else:
        if api_key and target_node:
            raw_output = generate_fake_log_by_ai(scenario_type, target_node, api_key)
            # エラー文字列が返ってきた場合のチェック
            if raw_output.startswith("Error"):
                return {"status": "ERROR", "sanitized_log": "", "error": raw_output}
            return {"status": "SUCCESS", "sanitized_log": sanitize_output(raw_output), "error": None}
        else:
            return {"status": "ERROR", "sanitized_log": "", "error": "API Key or Target Node Missing"}
