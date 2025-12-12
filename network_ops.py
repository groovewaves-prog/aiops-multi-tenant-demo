"""
Google Antigravity AIOps Agent - Network Operations Module
"""
import re
import os
import time
import google.generativeai as genai
from netmiko import ConnectHandler

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
    if not api_key: return "Error: API Key Missing"
    genai.configure(api_key=api_key)
    # ★変更: gemini-1.5-flash
    model = genai.GenerativeModel("gemini-1.5-flash")
    
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

    # --- Failure Context ---
    status_instructions = ""
    if "[FW]" in scenario_name:
        if "電源" in scenario_name and "片系" in scenario_name:
            status_instructions = "Junosコマンド `show chassis environment` で PSU 0: Failed, PSU 1: OK を表示せよ。"
        elif "FAN" in scenario_name:
            status_instructions = "Junosコマンド `show chassis environment` で Fan: Failed を表示せよ。"
        elif "メモリ" in scenario_name:
            status_instructions = "Junosコマンド `show system processes extensive` で特定プロセス(flowd等)がメモリを大量消費している様子を表示せよ。"
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
    シナリオ: {scenario_name}
    対象機器: {target_name} ({device_model}, {os_type})
    {status_instructions}
    出力ルール: 解説不要。CLIの生テキストのみ出力。障害原因を明確に。
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Generation Error: {e}"

def generate_config_from_intent(target_node, current_config, intent_text, api_key):
    if not api_key: return "Error: API Key Missing"
    genai.configure(api_key=api_key)
    # ★変更: gemini-1.5-flash
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    vendor = target_node.metadata.get("vendor", "Cisco")
    prompt = f"""
    ネットワーク設定生成。
    対象: {target_node.id} ({vendor})
    現在のConfig: {current_config}
    Intent: {intent_text}
    出力: コマンドのみ
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Config Gen Error: {e}"

def generate_health_check_commands(target_node, api_key):
    if not api_key: return "Error: API Key Missing"
    genai.configure(api_key=api_key)
    # ★変更: gemini-1.5-flash
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    vendor = target_node.metadata.get("vendor", "Cisco")
    prompt = f"Netmiko正常性確認コマンドを3つ生成せよ。対象: {vendor}。出力: コマンドのみ箇条書き"
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Command Gen Error: {e}"

def run_diagnostic_simulation(scenario_type, api_key=None):
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
            
    elif "全回線断" in scenario_type or "サイレント" in scenario_type or "両系" in scenario_type:
        return {"status": "ERROR", "sanitized_log": "", "error": "Connection timed out"}

    else:
        if api_key:
            raw_output = generate_fake_log_by_ai(scenario_type, api_key)
            return {"status": "SUCCESS", "sanitized_log": sanitize_output(raw_output), "error": None}
        else:
            return {"status": "ERROR", "sanitized_log": "", "error": "API Key Required"}
