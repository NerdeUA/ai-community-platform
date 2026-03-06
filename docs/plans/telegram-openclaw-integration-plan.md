# Plan: Telegram + OpenClaw + Core Agents Integration

This document outlines the architecture and implementation plan for making OpenClaw the primary Telegram bot interface for users, orchestrating requests to specialized agents (like `hello-world`) registered in the Core platform.

## 1. Architectural Overview

**The Flow:**

1. **User (Telegram):** Sends a message to the Telegram Bot (e.g., "Hey bot, what do you want to say to this world?").
2. **Telegram API:** Forwards the message to **OpenClaw** (via webhook or long-polling).
3. **OpenClaw (Orchestrator):**
   - Receives the message.
   - Uses its LLM to understand intent based on its System Prompt.
   - Knows about available tools (specialized agents) by pulling them from the **Core** `Discovery API`.
   - Decides to use the `hello-world` agent tool to answer the user's specific request.
4. **OpenClaw -> Core (A2A Bridge):** OpenClaw makes an HTTP call to the Core Platform's A2A Gateway endpoint (`/api/v1/a2a/send-message`) specifying the target `hello-world` and passing the context/arguments.
5. **Core -> Hello-World Agent:** Core validates the request and routes it to the `hello-world` agent's A2A endpoint.
6. **Hello-World Agent:** Processes the request natively (using its own logic/prompt) and returns a response.
7. **Response Chain:** The response travels back from Hello-World -> Core -> OpenClaw.
8. **OpenClaw (Formatting):** The LLM in OpenClaw reads the tool's output, wraps it in a conversational reply according to its persona, and sends it back to the Telegram API.

## 2. Setup Guide: Telegram Bot in OpenClaw

### Local Development (Polling Mode)

Locally, exposing a webhook is difficult due to NAT/firewalls. OpenClaw supports long-polling for local dev.

1. Create a bot via **BotFather** in Telegram and get the `TELEGRAM_BOT_TOKEN`.
2. In `docker/openclaw/.env`, add:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_WEBHOOK_URL=  # Leave empty for polling mode
   ```
3. Restart OpenClaw (`docker compose restart openclaw`). OpenClaw will start polling Telegram for updates.

### Production (Webhook Mode)

1. In the production `.env`, configure:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_WEBHOOK_URL=https://api.yourdomain.com/openclaw/webhook/telegram
   ```
2. **Traefik Configuration:** Ensure Traefik routes traffic to OpenClaw's webhook endpoint securely based on the domain rules.
3. OpenClaw will automatically register the webhook URL with Telegram on startup.

## 3. The "Hello World" Use Case (Step-by-Step)

1. **User Input:** "Hey bot, what do you want to say to this world?"
2. **Tool Discovery:**
   - OpenClaw periodically (or dynamically) fetches tools from Core (`GET /api/v1/a2a/discovery`).
   - It sees: `{"name": "hello-world", "description": "Responds with a greeting to the world."}`
3. **LLM Decision:** OpenClaw's central LLM recognizes the user is asking for the bot's message to the world, mapping perfectly to the `hello-world` tool.
4. **Tool Execution:** OpenClaw calls the Core:
   ```json
   POST /api/v1/a2a/send-message
   {
       "agent": "hello-world",
       "action": "run",
       "parameters": { "context": "user asked for a message to the world" }
   }
   ```
5. **Agent Logic:** The `hello-world` agent processes this via its internal prompt/logic: "Return 'Hello, World!' wrapped in a friendly sentence".
6. **Final Output:** OpenClaw takes the raw output ("Hello, World! I am an AI agent.") and replies to the Telegram user.

## 4. Required Implementation Steps (OpenSpec)

To achieve this, we need an `openspec` to cover:

1. **OpenClaw Telegram Channel Configuration:** Making sure the OpenClaw service is correctly configured to connect to Telegram in both dev and prod environments.
2. **OpenClaw Routing Instructions:** Providing a system prompt to OpenClaw so it knows _how_ to use the dynamically discovered agents and how to format responses for Telegram.
3. **Core A2A Invocation Bridge:** (Relies on the `add-openclaw-agent-discovery` and `add-hello-world-agent` specs being completed) to actually route the tool call from OpenClaw to the target agent.
