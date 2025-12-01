"""
Google Antigravity AIOps Agent - Network Operations Module
"""
import re
from netmiko import ConnectHandler

SANDBOX_DEVICE = {
    'device_type': 'cisco_ios',
    'host': 'sandbox-iosxe-latest-1.cisco.com',
    'username': 'developer',
    'password': 'C1sco12345',
    'port': 22,
}

def sanitize_output(text: str) -> str:
    # パスワードなどをマスク
    text = re.sub(r'(password|secret) \d+ \S+', r'\1 <HIDDEN>', text)
    text = re.sub(r'community \S+', 'community <HIDDEN>', text)
    return text

def run_diagnostic_commands():
    commands = [
        "show version | include Cisco IOS",
        "show ip interface brief",
        "show ip route summary",
    ]
    
    raw_output = ""
    status = "SUCCESS"
    error_msg = None

    try:
        with ConnectHandler(**SANDBOX_DEVICE) as ssh:
            ssh.enable()
            for cmd in commands:
                output = ssh.send_command(cmd)
                raw_output += f"\n[Command] {cmd}\n{output}\n"
                
    except Exception as e:
        status = "ERROR"
        error_msg = str(e)
        raw_output = f"SSH Connection Failed: {error_msg}"

    return {
        "status": status,
        "sanitized_log": sanitize_output(raw_output),
        "error": error_msg
    }