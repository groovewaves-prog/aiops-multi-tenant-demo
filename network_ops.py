"""
Google Antigravity AIOps Agent - Network Operations Module
"""
import re
import os
import time
import google.generativeai as genai
from netmiko import ConnectHandler

# Cisco DevNet Sandbox
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

def sanitize_output(text: str) -> str:
    rules = [
        (r'(password|secret) \d+ \S+', r'\1 <HIDDEN_PASSWORD>'),
        (r'(encrypted password) \S+', r'\1 <HIDDEN_PASSWORD>'),
        (r'(snmp-server community) \S+', r'\1 <HIDDEN_COMMUNITY>'),
        (r'(username \S+ privilege \d+ secret \d+) \S+', r'\1 <HIDDEN_SECRET>'),
        (r'\b(?!(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.)\d{1,3}\.(?:\d{1,3}\.){2}\d{1,3}\b', '<MASKED_PUBLIC_IP>'),
        (r'([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}', '<MASKED_MAC>'),
    ]
    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text)
    return text

def generate_fake_log_by_ai(scenario_name, api_key):
    """
    機器タイプと障害タイプを動的に組み合わせて、原因が明確なログを生成する
    """
    if not api_key: return "Error: API Key Missing"
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    # --- Device Context ---
    if "[FW]" in scenario_name:
        device_model = "Juniper SRX300"
        os_type = "Junos OS"
        target_name = "FW_01_PRIMARY"
    elif "[L2SW]" in scenario_name:
        device_model = "Cisco Catalyst 9300"
        os_type = "Cisco IOS-XE"
        target_name = "L2_SW_01"
    else:
        device_model = "Cisco ISR 4451-X"
        os_type = "Cisco IOS-XE"
        target_name = "WAN_ROUTER_01"

    # --- Failure Context (Junos対応などを追加) ---
    status_instructions = ""
    
    # FW (Juniper) の場合の指示
    if "[FW]" in scenario_name:
        if "電源" in scenario_name and "片系" in scenario_name:
            status_instructions = "Junosコマンド `show chassis environment` で PSU 0: Failed, PSU 1: OK を表示せよ。"
        elif "FAN" in scenario_name:
            status_instructions = "Junosコマンド `show chassis environment` で Fan: Failed を表示せよ。"
        elif "メモリ" in scenario_name:
            status_instructions = "Junosコマンド `show system processes extensive` で特定プロセス(flowd等)がメモリを大量消費している様子を表示せよ。"
    
    # Ciscoの場合 (既存ロジック維持)
    elif "電源" in scenario_name and "片系" in scenario_name:
        status_instructions = "IOSコマンド `show environment` で PS1: Fail を表示せよ。"
    elif "FAN" in scenario_name:
        status_instructions = "IOSコマンド `show environment` で Fan: Fail を表示せよ。"
    elif "メモリ" in scenario_name:
        status_instructions = "IOSコマンド `show processes memory` で特定プロセスがメモリ消費大であることを表示せよ。"
    elif "BGP" in scenario_name:
        status_instructions = "BGP Neighbor State が Idle/Active を繰り返すログにせよ。"
    elif "全回線断" in scenario_name:
        status_instructions = "Interface DOWN/DOWN, Ping 100% Loss."

    prompt = f"""
    あなたはネットワーク機器のCLIシミュレーターです。
    指定されたシナリオに基づき、トラブルシューティング用のコマンド実行結果（ログ）を生成してください。

    **対象機器**: {target_name} ({device_model}, {os_type})
    **シナリオ**: {scenario_name}

    {status_instructions}

    **出力ルール**:
    1. 解説不要。CLIの生テキストのみ出力。
    2. 対象OS ({os_type}) の正しいコマンドプロンプトと構文を使うこと。
    3. 障害原因が誰の目にも明らかになるように数値を強調すること。
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Generation Error: {e}"

# ★新規追加: Day 1 Config生成
def generate_config_from_intent(target_node, current_config, intent_text, api_key):
    if not api_key: return "Error: API Key Missing"
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    # メタデータからベンダー情報を取得
    vendor = target_node.metadata.get("vendor", "Cisco")
    os_type = target_node.metadata.get("os", "IOS")
    
    prompt = f"""
    あなたは熟練のネットワークエンジニアです。
    ユーザーの自然言語による指示(Intent)に基づき、ネットワーク機器の設定コマンド(Config)を生成してください。

    【対象機器情報】
    - Hostname: {target_node.id}
    - Vendor: {vendor}
    - OS: {os_type}

    【現在のConfig (参考)】
    ```
    {current_config}
    ```

    【ユーザーのIntent】
    "{intent_text}"

    【出力要件】
    1. 対象OS ({os_type}) でそのまま投入可能なコマンドセットを出力してください。
    2. 既存のConfigと矛盾しないようにしてください（例: 既に使われているIPは避ける、既存VLAN設定に合わせる等）。
    3. 危険なコマンド（全インターフェース停止など）が含まれる場合は警告を出してください。
    4. 出力はMarkdownのコードブロックで囲んでください。
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Config Gen Error: {e}"

# ★新規追加: マルチベンダー正常性確認コマンド生成
def generate_health_check_commands(target_node, api_key):
    if not api_key: return "Error: API Key Missing"
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    vendor = target_node.metadata.get("vendor", "Cisco")
    os_type = target_node.metadata.get("os", "IOS")
    
    prompt = f"""
    あなたはネットワーク自動化エンジニアです。
    Netmikoライブラリを使用して、対象機器の正常性確認（Health Check）を行いたいです。
    
    対象: {target_node.id} ({vendor} {os_type})
    
    この機器に対して実行すべき「状態確認用コマンド」を3つ～5つリストアップしてください。
    
    【出力形式】
    コマンドのみを箇条書きで出力してください。解説は不要です。
    例:
    show version
    show interfaces terse
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Command Gen Error: {e}"

def run_diagnostic_simulation(scenario_type, api_key=None):
    time.sleep(1.5)
    
    status = "SUCCESS"
    raw_output = ""
    error_msg = None

    if "---" in scenario_type or "正常" in scenario_type:
        return {"status": "SKIPPED", "sanitized_log": "No action required.", "error": None}

    if "[Live]" in scenario_type:
        # (Netmikoコード省略)
        raw_output = "Connected to Cisco Sandbox (Simulated for this context)"
            
    elif "全回線断" in scenario_type or "サイレント" in scenario_type or "両系" in scenario_type:
        status = "ERROR"
        error_msg = "Connection timed out"
        raw_output = "SSH Connection Failed. Host Unreachable. (No Response from Console)"

    else:
        if api_key:
            raw_output = generate_fake_log_by_ai(scenario_type, api_key)
        else:
            status = "ERROR"
            error_msg = "API Key Required"
            raw_output = "Cannot generate logs without API Key."

    return {
        "status": status,
        "sanitized_log": sanitize_output(raw_output),
        "error": error_msg
    }
