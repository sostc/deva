---
name: "openclaw"
description: "Comprehensive OpenClaw (also known as '龙虾' or '任意虾') manager. Use this skill to Install OpenClaw (with safety checks) AND Initialize/Configure it (Feishu integration, models, agents)."
---

# OpenClaw Manager

This skill provides a complete suite for managing OpenClaw, including installation and initialization.

**Keywords**: OpenClaw, 龙虾 (Lobster), 任意虾 (Any Shrimp)

## Capabilities

1.  **Install**: Installs nvm, Node.js 22, and OpenClaw with safety warnings.
2.  **Initialize**: Configures Feishu integration, models (Doubao or Anthropic), agents, and starts the service using a robust configuration script.
3.  **Manage Service**: Restarts, stops, and checks the status of the OpenClaw service.

---

## Part 1: Install OpenClaw

Follow these steps if the user needs to install OpenClaw.

### Step 0: Safety Warning and Confirmation

**⚠️ IMPORTANT SAFETY NOTICE**

Before proceeding, please note:
For security reasons and system stability, it is **strongly recommended** to:
1.  Use a **spare computer** for this installation, OR
2.  Create a **separate user account** on your main computer and switch to that account before installing.

This practice helps isolate the OpenClaw environment and prevents potential conflicts with your main system configuration.

**Please confirm with the user:**
"Have you switched to a spare computer or a separate user account? Do you wish to proceed with the installation?"

**Only proceed to Step 1 after the user confirms.**

### Step 1: Install Node Version Manager (nvm)

If you don't have nvm installed, follow these steps:

1. Open Terminal.
2. Run the following command to install nvm, activate it, and verify the version:
   ```bash
   touch ~/.zshrc && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && source ~/.zshrc && nvm --version
   ```
   If successful, it will display the nvm version (e.g., v0.39.7).

### Step 2: Install Node.js for OpenClaw

OpenClaw requires Node.js version ≥22.

1. Install Node.js 22, use it, and verify version:
   ```bash
   nvm install 22 && nvm use 22 && node -v
   ```
   Should display v22.x.x.

### Step 3: Install OpenClaw

1. Install OpenClaw globally and verify installation:
   ```bash
   npm install -g openclaw && openclaw --version
   ```
   Should display the version number (e.g., 2026.2.25).

---

## Part 2: Initialize OpenClaw Configuration

Follow these steps to configure OpenClaw after installation. This process uses a **Python script** to safely configure Authentication, Models, Agents, and Feishu integration.

### Step 1: Gather Configuration Information

Ask the user which model provider they want to use (**Doubao** or **Anthropic**) and gather the corresponding information.

**For Doubao (Volcano Ark):**
1.  **Doubao API Key**: The API key.
2.  **Doubao Model Endpoint ID**: The endpoint ID (e.g., `ep-20240604052306-abcde`).
3.  **Doubao Model Name**: The model name (e.g., `Doubao-1.8`).
4.  **Feishu App ID** & **App Secret**.

**For Anthropic:**
1.  **Anthropic API Key**: The API key.
2.  **Model Name**: The model name (e.g., `claude-3-5-sonnet-20240620`).
3.  **Feishu App ID** & **App Secret**.

### Step 2: Execute Configuration Script

Instead of running raw CLI commands, create and run the configuration script.

1.  **Create the Script**:
    Create a file named `configure_openclaw.py` with the content provided in the skill package (or copy it from the source if available).
    *(Note: If the script is not present, the agent should generate it. It supports `--provider` argument.)*

2.  **Run the Script**:
    Execute the script with the user's parameters.

    **For Doubao:**
    ```bash
    python3 configure_openclaw.py --provider doubao --api-key "YOUR_API_KEY" --endpoint-id "YOUR_ENDPOINT_ID" --model-name "YOUR_MODEL_NAME" --feishu-app-id "YOUR_APP_ID" --feishu-app-secret "YOUR_APP_SECRET"
    ```

    **For Anthropic:**
    ```bash
    python3 configure_openclaw.py --provider anthropic --api-key "YOUR_API_KEY" --model-name "claude-3-5-sonnet-20240620" --feishu-app-id "YOUR_APP_ID" --feishu-app-secret "YOUR_APP_SECRET"
    ```

### Step 3: Install Feishu Plugin (If not already installed)

Ensure the Feishu plugin is installed:

```bash
openclaw plugins install @openclaw/feishu
```

### Step 4: Restart Service and Verify

1.  Restart the OpenClaw gateway service and check status:
    ```bash
    openclaw gateway restart && openclaw gateway status
    ```
2.  **Success**: Inform the user if the status shows "running" or similar positive output.
3.  **Failure**: If the service fails, prompt the user to check logs or try running the start command manually.

### Step 5: Post-Configuration Instructions

After the service has restarted successfully, you **MUST** provide the following instructions to the user to complete the integration.

1.  **Construct the Event Subscription URL**:
    Use the Feishu App ID provided by the user (`YOUR_FEISHU_APP_ID`) to construct the URL:
    `https://open.larkoffice.com/app/YOUR_FEISHU_APP_ID/event`
    *(Example: if App ID is `cli_a0a2b2f880b89013`, the URL is `https://open.larkoffice.com/app/cli_a0a2b2f880b89013/event`)*

2.  **Instruct the User**:
    "Please visit the following URL to configure Event Subscriptions and publish your app version:
    [Feishu Event Configuration](https://open.larkoffice.com/app/YOUR_FEISHU_APP_ID/event)

    **Next Steps:**
    1.  Go to **Event Subscriptions** in the Feishu Developer Console.
    2.  Configure the Request URL (usually your OpenClaw server's public URL).
    3.  Create a **Version** and **Publish** your app for the changes to take effect."

---

## Part 3: Manage OpenClaw Service

Use these commands to manage the OpenClaw service lifecycle.

### Restart Service

1.  Execute the restart command and verify status:
    ```bash
    openclaw gateway restart && openclaw gateway status
    ```
2.  **Verify Status**:
    -   **If Status is Running**: Inform the user "Service restarted successfully."
    -   **If Status is Failed/Not Running**:
        -   Check if the service is installed. If not, suggest running: `openclaw gateway install`
        -   Check logs for errors.

### Stop Service

1.  Execute the stop command and verify status:
    ```bash
    openclaw gateway stop && openclaw gateway status
    ```
