import json
import httpx
from typing import Optional, List, Dict

DEFAULT_TIMEOUT = httpx.Timeout(60.0, read=120.0)

class LLMTimeoutError(Exception):
    """Raised when an LLM API call times out."""
    pass

def complete(
    prompt: str,
    provider: str,
    config: dict,
    system: str = "",
    tools: Optional[List[dict]] = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
) -> dict:
    """
    Non-streaming HTTP call to LLM provider.
    Raises LLMTimeoutError on timeout to prevent hanging.
    Returns: {"content": "...", "tool_calls": [...]}
    """
    api_key = config.get("api_key", "")
    model = config.get("model", "")
    base_url = config.get("base_url", "")

    if provider == "claude":
        url = f"{base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "stream": False,
        }
        if system:
            payload["system"] = system

        if tools:
            payload["tools"] = tools

        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()

            content = ""
            tool_calls = []

            for block in data.get("content", []):
                if block["type"] == "text":
                    content += block["text"]
                elif block["type"] == "tool_use":
                    tool_calls.append({
                        "name": block["name"],
                        "arguments": block["input"]
                    })

            return {"content": content, "tool_calls": tool_calls}

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"Claude API timed out: {e}")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Claude API error: {e.response.status_code} - {e.response.text}")

    elif provider == "openai_compat":
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        if tools:
            # Note: For strict compatibility, tools format should be OpenAI format
            # In aic, we'll map the basic tool schema if provided as-is
            payload["tools"] = []
            for tool in tools:
                if "type" not in tool:
                    # Convert from Claude format to OpenAI if needed
                    payload["tools"].append({
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                        }
                    })
                else:
                    payload["tools"].append(tool)

        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]["message"]
            content = choice.get("content") or ""
            tool_calls = []

            for call in choice.get("tool_calls", []):
                if call["type"] == "function":
                    args_str = call["function"].get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append({
                        "name": call["function"]["name"],
                        "arguments": args
                    })

            return {"content": content, "tool_calls": tool_calls}

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"OpenAI compat API timed out: {e}")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"OpenAI compat API error: {e.response.status_code} - {e.response.text}")

    else:
        raise ValueError(f"Unknown provider: {provider}")
