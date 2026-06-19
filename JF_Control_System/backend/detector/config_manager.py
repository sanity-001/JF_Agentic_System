import re
from typing import Dict, List

PARAM_SCHEMA = {
    "hostname":     {"type": "str", "required": True},
    "rx_hostname":  {"type": "str", "required": False},
    "udp_srcip":    {"type": "str", "required": False},
    "udp_dstip":    {"type": "str", "required": False},
    "powerchip":    {"type": "int", "required": False, "range": (0, 1)},
    "highvoltage":  {"type": "int", "required": False, "range": (0, 200)},
    "timing":       {"type": "str", "required": False, "choices": ["auto", "trigger"]},
    "exptime":      {"type": "duration", "required": False},
    "period":       {"type": "duration", "required": False},
    "frames":       {"type": "int", "required": False, "range": (1, 100000000)},
    "fpath":        {"type": "str", "required": False},
    "fwrite":       {"type": "int", "required": False, "range": (0, 1)},
    "readoutspeed": {"type": "str", "required": False, "choices": ["full_speed", "half_speed", "quarter_speed"]},
    "detsize":      {"type": "str", "required": False},
}

# 4M per-module keys (0:udp_srcip, 0:udp_dstip, 0:rx_tcpport, etc.) match any "N:key" pattern.
# These keys are not in PARAM_SCHEMA and are therefore skipped during validation.
# Values are passed directly to the slsdet library, which handles its own validation.


def parse_config(text: str) -> Dict[str, str]:
    result = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            result[parts[0]] = parts[1]
    return result


def generate_config(params: Dict[str, str]) -> str:
    lines = [f"{k} {v}" for k, v in params.items()]
    return "\n".join(lines) + "\n"


def validate_params(params: Dict[str, str]) -> List[str]:
    errors = []
    for key, value in params.items():
        schema = PARAM_SCHEMA.get(key)
        if not schema:
            continue
        if schema["type"] == "int":
            try:
                ival = int(value)
                r = schema.get("range")
                if r and not (r[0] <= ival <= r[1]):
                    errors.append(f"{key}: value {ival} out of range {r}")
            except ValueError:
                errors.append(f"{key}: expected int, got '{value}'")
        elif schema["type"] == "duration":
            if not re.match(r"^\d+(\.\d+)?\s*(ns|us|ms|s)$", value.strip()):
                errors.append(f"{key}: invalid duration '{value}' (e.g. 100us, 1ms, 0.5s)")
        elif schema["type"] == "str":
            choices = schema.get("choices")
            if choices and value not in choices:
                errors.append(f"{key}: '{value}' not in {choices}")
    return errors


def detect_detector_type(params: Dict[str, str]) -> str:
    """根据配置参数自动判断探测器类型.

    判断依据（满足任一即可）：
    1. 存在 detsize 键
    2. hostname 包含 '+'（多模块连接）
    3. 存在 '0:udp_srcip' 等逐模块键（以 "数字:" 开头的键）
    """
    if "detsize" in params:
        return "4M"
    hostname = params.get("hostname", "")
    if "+" in hostname:
        return "4M"
    for key in params:
        if ":" in key and key.split(":")[0].isdigit():
            return "4M"
    return "500K"
