import pandas as pd
import random

# 生成するデータ数（多ければ多いほど確率が安定します）
NUM_SAMPLES = 5000

# ■ 世界の法則（シナリオ定義）
# ここで「Aが起きたらBが出やすい」という確率的な因果関係を定義します。
SCENARIOS = [
    # シナリオ1: WANルーターの物理故障（桶屋シナリオ）
    # BGPが揺れるが、真因は物理ハードウェア。I/Fダウンが決定的な証拠。
    {
        "root_cause_id": "WAN_ROUTER_01",
        "root_cause_type": "Hardware/Physical",
        "weight": 0.2, 
        "probabilities": {
            ("alarm", "BGP Flapping"): 0.70,     # 物理層の影響でBGPも揺れる
            ("log", "Interface Down"): 0.95,     # 物理故障ならほぼ確実に出る（強い証拠）
            ("ping", "NG"): 0.90,
            ("log", "Power Fail"): 0.10
        }
    },
    # シナリオ2: WANルーターの設定ミス
    # BGPは揺れるが、物理I/Fは落ちていないことが多い。
    {
        "root_cause_id": "WAN_ROUTER_01",
        "root_cause_type": "Config/Software",
        "weight": 0.3,
        "probabilities": {
            ("alarm", "BGP Flapping"): 0.85,     # 設定ミスなのでBGPエラーは頻発
            ("log", "Interface Down"): 0.05,     # 設定ミスで物理リンク断は稀
            ("ping", "NG"): 0.30,                # 疎通可能な場合もある
            ("log", "Config Error"): 0.80
        }
    },
    # シナリオ3: FWのハードウェア障害
    {
        "root_cause_id": "FW_01_PRIMARY",
        "root_cause_type": "Hardware/Physical",
        "weight": 0.1,
        "probabilities": {
            ("alarm", "HA Failover"): 0.90,
            ("ping", "NG"): 0.50,
            ("log", "Power Fail"): 0.80
        }
    },
    # シナリオ4: 外部ISP障害（ノイズ）
    # こちらの機器は正常だが通信できないパターン
    {
        "root_cause_id": "External_ISP",
        "root_cause_type": "Network",
        "weight": 0.2,
        "probabilities": {
            ("alarm", "BGP Flapping"): 0.60,
            ("log", "Interface Down"): 0.01,     # ISP側の問題なのでこちらのIFはUP
            ("ping", "NG"): 0.80
        }
    }
]

def generate_mock_data():
    data = []
    
    print(f"Generating {NUM_SAMPLES} training samples based on World Model...")
    
    for _ in range(NUM_SAMPLES):
        # 1. 確率的重みに基づいて、どの障害シナリオが発生したか抽選
        scenario = random.choices(SCENARIOS, weights=[s["weight"] for s in SCENARIOS])[0]
        root_key = f"{scenario['root_cause_id']}::{scenario['root_cause_type']}"
        
        # 2. そのシナリオにおいて、どの証拠(Evidence)が観測されるかシミュレーション
        for (ev_type, ev_val), prob in scenario["probabilities"].items():
            # 確率 prob で証拠が発生する
            if random.random() < prob:
                data.append({
                    "RootCause": root_key,
                    "EvidenceType": ev_type,
                    "EvidenceValue": ev_val
                })
        
        # ノイズ: たまに無関係な謎のエラーが出る
        if random.random() < 0.05:
            data.append({
                "RootCause": root_key,
                "EvidenceType": "log",
                "EvidenceValue": "Unknown Error"
            })

    # CSVとして保存
    df = pd.DataFrame(data)
    df.to_csv("training_data.csv", index=False)
    print(f"✅ Saved 'training_data.csv' ({len(df)} records).")

if __name__ == "__main__":
    generate_mock_data()
