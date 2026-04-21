"""
L0 入口层：argparse，参数解析，调起 repl
"""

import argparse
from aic import repl
from aic import config

def main():
    parser = argparse.ArgumentParser(description="aic — AI Coding Assistant")
    parser.add_argument("--provider", type=str, help="LLM Provider to use (e.g., deepseek, claude)")
    parser.add_argument("--model", type=str, help="Model name to use")
    args = parser.parse_args()

    cfg = config.get_config()

    if args.provider:
        cfg["provider"] = args.provider

    if args.model:
        provider_name = cfg.get("provider", "deepseek")
        if provider_name not in cfg:
            cfg[provider_name] = {}
        cfg[provider_name]["model"] = args.model

    repl.start(cfg)

if __name__ == "__main__":
    main()
