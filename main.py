"""
Google Antigravity AIOps Agent - メインモジュール
CLIエントリーポイントおよびAI統合。
"""

import os
import sys
import time
import google.generativeai as genai
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

from data import TOPOLOGY, SOPS, NetworkNode
from logic import CausalInferenceEngine, Alarm

# Richコンソールの初期化
console = Console()

def print_header():
    console.clear()
    console.print(Panel.fit(
        "[bold white]GOOGLE ANTIGRAVITY[/bold white]\n[cyan]自律型 AIOps エージェント[/cyan]",
        style="bold blue",
        subtitle="v1.0.0"
    ))

def check_api_key():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        console.print("[bold red]エラー: 環境変数に GOOGLE_API_KEY が見つかりません。[/bold red]")
        console.print("続行するにはAPIキーを設定してください。")
        sys.exit(1)
    genai.configure(api_key=api_key)

def generate_ai_report(inference_result, sop_content):
    """
    Geminiを使用して自然言語レポートを生成します。
    """
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
    
    prompt = f"""
    あなたは「Antigravity Agent」、高度なAIOpsアシスタントです。
    
    **コンテキスト**:
    ネットワーク障害が発生しました。因果推論エンジンが根本原因を特定しました。
    
    **根本原因**: {inference_result.root_cause_reason}
    **影響デバイス**: {inference_result.root_cause_node.id if inference_result.root_cause_node else "不明"}
    **推奨SOP**:
    {sop_content}
    
    **タスク**:
    ネットワークオペレーションセンター (NOC) 向けの簡潔でプロフェッショナルなインシデントレポートを作成してください。
    言語は日本語でお願いします。
    1. インシデントの概要を要約してください。
    2. なぜこれが根本原因なのか（ロジックを参照して）説明してください。
    3. SOPのアクションアイテムを明確に提示してください。
    4. 未来的で自信に満ちた「Antigravity」のトーンを維持してください。
    """
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="[cyan]Antigravity Core 処理中...[/cyan]", total=None)
        response = model.generate_content(prompt)
        
    return response.text

def run_scenario(scenario_id):
    engine = CausalInferenceEngine(TOPOLOGY)
    alarms = []
    
    if scenario_id == "1":
        # WAN 全断
        alarms = [
            Alarm("WAN_ROUTER_01", "Interface Down", "CRITICAL"),
            Alarm("FW_01_PRIMARY", "Gateway Unreachable", "WARNING"),
            Alarm("CORE_SW_01", "Uplink Down", "WARNING"),
            Alarm("AP_01", "Controller Unreachable", "CRITICAL")
        ]
    elif scenario_id == "2":
        # FW 片系障害
        alarms = [
            Alarm("FW_01_PRIMARY", "Heartbeat Loss", "WARNING"),
            Alarm("FW_01_PRIMARY", "System Crash", "CRITICAL")
        ]
    elif scenario_id == "3":
        # L2 サイレント障害
        # L2_SW_01 からのアラームはないが、配下のAPが全滅
        alarms = [
            Alarm("AP_01", "Connection Lost", "CRITICAL"),
            Alarm("AP_02", "Connection Lost", "CRITICAL")
        ]
    else:
        console.print("[red]無効なシナリオです[/red]")
        return

    # アラーム表示
    table = Table(title="受信テレメトリストリーム")
    table.add_column("デバイス", style="cyan")
    table.add_column("重要度", style="magenta")
    table.add_column("メッセージ", style="white")
    
    for alarm in alarms:
        table.add_row(alarm.device_id, alarm.severity, alarm.message)
    
    console.print(table)
    console.print("\n[bold yellow]因果推論エンジンを実行中...[/bold yellow]")
    time.sleep(1) # 処理シミュレーション
    
    result = engine.analyze_alarms(alarms)
    
    console.print(f"[bold green]特定された根本原因:[/bold green] {result.root_cause_reason}")
    
    # SOP取得
    sop = SOPS.get(result.sop_key, SOPS["DEFAULT"])
    
    # AIレポート生成
    console.print("\n[bold purple]Antigravity レポートを生成中...[/bold purple]")
    try:
        report = generate_ai_report(result, sop)
        console.print(Panel(Markdown(report), title="Antigravity Agent レポート", border_style="green"))
    except Exception as e:
        console.print(f"[bold red]AI生成失敗:[/bold red] {e}")
        console.print(Panel(Markdown(sop), title="フォールバック SOP (手動モード)", border_style="yellow"))

def main():
    print_header()
    try:
        check_api_key()
    except SystemExit:
        # デモ用にキーなしでも続行可能にするが警告を表示
        pass

    while True:
        console.print("\n[bold]障害シミュレーションを選択してください:[/bold]")
        console.print("1. WAN 全断 (階層ルール)")
        console.print("2. FW 片系障害 (冗長性ルール)")
        console.print("3. L2スイッチ サイレント障害 (推論ルール)")
        console.print("q. 終了")
        
        choice = Prompt.ask("選択してください", choices=["1", "2", "3", "q"], default="1")
        
        if choice == "q":
            break
            
        run_scenario(choice)
        
        if Prompt.ask("\n別のシミュレーションを実行しますか？", choices=["y", "n"], default="y") == "n":
            break

if __name__ == "__main__":
    main()
