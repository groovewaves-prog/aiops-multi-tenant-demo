"""
Verification script for Antigravity AIOps Agent Logic (Japanese)
"""
import sys
from data import TOPOLOGY, SOPS
from logic import CausalInferenceEngine, Alarm

def test_wan_failure():
    print("Testing WAN Failure (Hierarchy Rule)...")
    engine = CausalInferenceEngine(TOPOLOGY)
    alarms = [
        Alarm("WAN_ROUTER_01", "Interface Down", "CRITICAL"),
        Alarm("FW_01_PRIMARY", "Gateway Unreachable", "WARNING"),
        Alarm("CORE_SW_01", "Uplink Down", "WARNING"),
        Alarm("AP_01", "Controller Unreachable", "CRITICAL")
    ]
    result = engine.analyze_alarms(alarms)
    assert result.root_cause_node.id == "WAN_ROUTER_01"
    assert result.sop_key == "WAN_FAILURE"
    print("PASS")

def test_fw_redundancy():
    print("Testing FW Redundancy (Redundancy Rule)...")
    engine = CausalInferenceEngine(TOPOLOGY)
    alarms = [
        Alarm("FW_01_PRIMARY", "Heartbeat Loss", "WARNING"),
        Alarm("FW_01_PRIMARY", "System Crash", "CRITICAL")
    ]
    result = engine.analyze_alarms(alarms)
    assert result.root_cause_node.id == "FW_01_PRIMARY"
    assert result.sop_key == "FW_HA_WARNING"
    print("PASS")

def test_silent_failure():
    print("Testing Silent Failure (Inference Rule)...")
    engine = CausalInferenceEngine(TOPOLOGY)
    # APs are down, but L2 switch (L2_SW_01) has no alarm
    alarms = [
        Alarm("AP_01", "Connection Lost", "CRITICAL"),
        Alarm("AP_02", "Connection Lost", "CRITICAL")
    ]
    result = engine.analyze_alarms(alarms)
    assert result.root_cause_node.id == "L2_SW_01"
    assert result.sop_key == "L2_SILENT_FAILURE"
    print("PASS")

if __name__ == "__main__":
    try:
        test_wan_failure()
        test_fw_redundancy()
        test_silent_failure()
        print("\nALL TESTS PASSED")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
