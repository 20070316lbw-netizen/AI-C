"""
L0 入口层：argparse，参数解析，调起 repl
"""

import argparse
from aic import repl

def main():
    parser = argparse.ArgumentParser(description="aic — AI Coding Assistant")
    parser.add_argument("--provider", type=str, help="LLM Provider to use (e.g., deepseek, claude)")
    parser.add_argument("--model", type=str, help="Model name to use")
    args = parser.parse_args()

    repl.start()

if __name__ == "__main__":
    main()
