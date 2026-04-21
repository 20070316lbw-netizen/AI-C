"""
L1 会话层：config.toml 加载/保存，env 覆盖
"""
import os
import tomllib
from pathlib import Path
import copy

DEFAULT_CONFIG = {
    "provider": "deepseek",
    "claude": {
        "api_key": "",
        "model": "claude-sonnet-4-20250514",
        "base_url": "https://api.anthropic.com"
    },
    "deepseek": {
        "api_key": "",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com"
    },
    "gemini": {
        "api_key": "",
        "model": "gemini-2.5-pro",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"
    },
    "dream": {
        "min_unprocessed": 20,
        "min_interval_h": 24,
        "min_sessions": 5,
        "lock_timeout_h": 1,
        "model": "deepseek-chat"
    }
}

def get_config() -> dict:
    """
    加载配置。
    优先级：环境变量 > config.toml > 代码默认值
    """
    config = copy.deepcopy(DEFAULT_CONFIG)

    config_path = Path("~/.config/aic/config.toml").expanduser()

    if config_path.is_file():
        try:
            with open(config_path, "rb") as f:
                toml_config = tomllib.load(f)

            for k, v in toml_config.items():
                if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                    config[k].update(v)
                else:
                    config[k] = v
        except OSError:
            # 文件不存在等 OS 级别错误时使用默认值，不报错
            pass

    # 环境变量覆盖
    if "AIC_PROVIDER" in os.environ:
        config["provider"] = os.environ["AIC_PROVIDER"]

    if "ANTHROPIC_API_KEY" in os.environ:
        config.setdefault("claude", {})["api_key"] = os.environ["ANTHROPIC_API_KEY"]

    if "DEEPSEEK_API_KEY" in os.environ:
        config.setdefault("deepseek", {})["api_key"] = os.environ["DEEPSEEK_API_KEY"]

    if "GEMINI_API_KEY" in os.environ:
        config.setdefault("gemini", {})["api_key"] = os.environ["GEMINI_API_KEY"]

    return config
