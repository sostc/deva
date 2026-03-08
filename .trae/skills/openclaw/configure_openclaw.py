import subprocess
import json
import argparse
import sys

def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def set_config_recursive(path_parts, full_config_dict):
    """
    Starting from root, check each node. If missing, set the node's entire subtree as a JSON string.
    """
    for i in range(1, len(path_parts) + 1):
        current_path = ".".join(path_parts[:i])
        
        # 1. Check if node exists
        check_cmd = f"openclaw config get {current_path}"
        output = run_command(check_cmd)
        
        # 2. If node is missing or undefined
        if not output or output == "undefined":
            print(f"Path '{current_path}' is missing. Setting its content...")
            
            # Extract the subtree for this node from full_config_dict
            subtree = full_config_dict
            for part in path_parts[:i]:
                subtree = subtree.get(part, {})
            
            # Convert subtree to JSON string
            json_value = json.dumps(subtree)
            
            # Execute set command for this node
            set_cmd = f"openclaw config set {current_path} '{json_value}'"
            if run_command(set_cmd) is None:
                print(f"Failed to set node: {current_path}")
            else:
                print(f"Successfully initialized node: {current_path}")
            
            # Once we've set a node's entire subtree, all its children are implicitly created.
            break
        else:
            print(f"Path '{current_path}' exists.")

def main():
    parser = argparse.ArgumentParser(description="Configure OpenClaw for Doubao or Anthropic")
    parser.add_argument("--provider", choices=["doubao", "anthropic"], default="doubao", help="Model provider (doubao or anthropic)")
    parser.add_argument("--api-key", required=True, help="API Key for the provider")
    parser.add_argument("--endpoint-id", help="Endpoint ID (Required for Doubao, usually the model ID for Anthropic)")
    parser.add_argument("--model-name", required=True, help="Model Name (e.g., Doubao-1.8 or claude-3-5-sonnet-20240620)")
    parser.add_argument("--feishu-app-id", required=True, help="Feishu App ID")
    parser.add_argument("--feishu-app-secret", required=True, help="Feishu App Secret")

    args = parser.parse_args()

    # Determine provider-specific settings
    provider = args.provider
    api_key = args.api_key
    model_name = args.model_name
    feishu_app_id = args.feishu_app_id
    feishu_app_secret = args.feishu_app_secret

    # For Doubao, endpoint_id is required. For Anthropic, we use model_name as ID if endpoint_id is missing.
    if provider == "doubao":
        if not args.endpoint_id:
            print("Error: --endpoint-id is required for Doubao provider.")
            sys.exit(1)
        endpoint_id = args.endpoint_id
        base_url = "https://ark.cn-beijing.volces.com/api/v3"
        api_type = "openai-completions"
        agent_model_ref = f"doubao/{endpoint_id}"
        models_config = [{"id": endpoint_id, "name": model_name}]
    elif provider == "anthropic":
        # Anthropic doesn't need endpoint_id in the same way, usually just model ID.
        # We'll use endpoint_id if provided, otherwise model_name.
        endpoint_id = args.endpoint_id if args.endpoint_id else model_name
        base_url = "https://api.anthropic.com" # Default Anthropic API URL
        api_type = "anthropic-chat" # Assuming this is the OpenClaw key for Anthropic
        agent_model_ref = f"anthropic/{endpoint_id}"
        models_config = [{"id": endpoint_id, "name": model_name}]

    # Build the configuration dictionary
    full_config = {
        "auth": {
            "profiles": {
                f"{provider}:default": {
                    "provider": provider,
                    "mode": "api_key"
                }
            }
        },
        "models": {
            "providers": {
                provider: {
                    "baseUrl": base_url,
                    "apiKey": api_key,
                    "api": api_type, # This might differ for Anthropic, assuming OpenClaw supports 'anthropic' or generic OpenAI
                    "models": models_config
                }
            }
        },
        "agents": {
            "defaults": {
                "model": {
                    "primary": agent_model_ref
                },
                "models": {
                    agent_model_ref: provider
                },
                "workspace": "~/.openclaw/workspace",
                "compaction": {
                    "mode": "safeguard"
                },
                "maxConcurrent": 4,
                "subagents": {
                    "maxConcurrent": 8
                }
            }
        },
        "messages": {
            "ackReactionScope": "group-mentions"
        },
        "commands": {
            "native": "auto",
            "nativeSkills": "auto",
            "restart": True,
            "ownerDisplay": "raw"
        },
        "session": {
            "dmScope": "per-channel-peer"
        },
        "channels": {
            "feishu": {
                "appId": feishu_app_id,
                "appSecret": feishu_app_secret,
                "enabled": True
            }
        },
        "plugins": {
            "entries": {
                "feishu": {
                    "enabled": True
                }
            }
        }
    }

    print(f"Starting OpenClaw Hierarchical Configuration for {provider}...")

    # Root paths to check
    root_paths = [
        f"auth.profiles.{provider}:default",
        f"models.providers.{provider}",
        "agents.defaults",
        "messages",
        "commands",
        "session",
        "channels.feishu",
        "plugins.entries.feishu"
    ]

    for path in root_paths:
        path_parts = path.split('.')
        set_config_recursive(path_parts, full_config)

    print("\nConfiguration process completed.")

if __name__ == "__main__":
    main()
