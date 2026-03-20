#!/usr/bin/env python3
"""
Test script to demonstrate end-to-end tracing in Jennifer Bot.

Covers the current architecture after refactor:
  - Per-message model routing via route_and_update_config
  - _verified_agents dict-based cache (agent_id -> model)
  - NSFW tier detection -> _nsfw_mode=True
  - Fallback chain using full provider paths
  - Agent recreation via dict.pop() (not set.remove())
"""

import asyncio
import sys
sys.path.insert(0, '/app')

from core.tracing import get_tracer, SpanStatus

tracer = get_tracer()


async def simulate_discord_message():
    """Simulate a full !draw message flow with tracing."""

    print("=" * 70)
    print("SIMULATING: Discord Message → Image Generation Flow")
    print("=" * 70)

    trace_id = tracer.start_trace(
        "discord_message",
        attributes={
            "user_id": "123456789",
            "user_name": "TestUser",
            "channel_id": "987654321",
            "content_preview": "!draw a beautiful sunset",
        }
    )

    try:
        tracer.add_event("message_received")

        filter_span = tracer.start_span("filter_checks", "discord")
        await asyncio.sleep(0.01)
        tracer.add_event("filters_passed")
        tracer.end_span(filter_span)

        cmd_span = tracer.start_span("handle_draw_command", "discord")
        tracer.add_attribute("command", "draw")
        tracer.add_event("queued_image_task")

        gen_span = tracer.start_span("generate_image", "image_gen", parent_id=cmd_span)
        tracer.add_event("creating_adapter")
        tracer.add_attribute("backend", "comfyui")

        comfy_span = tracer.start_span("comfyui_generate", "comfyui", parent_id=gen_span)
        tracer.add_event("queueing_prompt")
        await asyncio.sleep(0.05)
        tracer.add_attribute("prompt_id", "abc-123-xyz")
        tracer.add_event("prompt_queued")

        tracer.add_event("polling_for_completion")
        await asyncio.sleep(0.1)
        tracer.add_event("workflow_completed", {"attempts": 5})

        tracer.add_event("fetching_image")
        await asyncio.sleep(0.02)
        tracer.add_event("image_fetched", {"size_bytes": 245760})

        tracer.end_span(comfy_span, SpanStatus.SUCCESS)
        tracer.end_span(gen_span, SpanStatus.SUCCESS)
        tracer.end_span(cmd_span, SpanStatus.SUCCESS)

        tracer.add_event("response_sent")
        tracer.end_trace(trace_id)

        print("\n✅ Image generation trace completed!")

    except Exception as e:
        tracer.add_event("error", {"error": str(e)})
        tracer.end_trace(trace_id)
        print(f"\n❌ Trace failed: {e}")


async def simulate_openclaw_conversation():
    """Simulate OpenClaw conversation with per-message model routing.

    Reflects the current flow:
      route_and_update_config → ensure_agent_exists (_verified_agents dict check) → send_message
    """

    print("\n" + "=" * 70)
    print("SIMULATING: OpenClaw Conversation with Model Routing")
    print("=" * 70)

    trace_id = tracer.start_trace(
        "openclaw_conversation",
        attributes={
            "user_id": "123456789",
            "user_name": "TestUser",
            "message": "Can you help me debug this Python code?",
        }
    )

    try:
        # Model routing — happens on every message
        route_span = tracer.start_span("route_and_update_config", "openclaw")
        tracer.add_event("routing_message", {"tier": "intelligence"})
        tracer.add_attribute("routed_model", "openai-codex/gpt-5.3-codex")
        tracer.add_attribute("score", 0.78)
        tracer.add_attribute("reason", "keyword:debug complexity:high")
        tracer.add_event("config_updated", {"model": "openai-codex/gpt-5.3-codex"})
        tracer.end_span(route_span)

        # Agent verification — dict keyed by agent_id -> last_verified_model
        agent_span = tracer.start_span("ensure_agent_exists", "openclaw")
        tracer.add_attribute("agent_id", "jennifer-user-123456789")
        tracer.add_attribute("primary_model", "openai-codex/gpt-5.3-codex")
        tracer.add_event("cache_miss", {"reason": "model changed since last request"})
        tracer.add_event("rpc_config_get")
        await asyncio.sleep(0.02)
        tracer.add_event("config_patched", {"agent": "jennifer-user-123456789"})
        tracer.add_event("cache_updated", {"agent_id": "jennifer-user-123456789",
                                            "model": "openai-codex/gpt-5.3-codex"})
        tracer.end_span(agent_span)

        # Message send — full model path, no prefix stripping
        send_span = tracer.start_span("send_message", "openclaw")
        tracer.add_attribute("model_id", "openai-codex/gpt-5.3-codex")
        tracer.add_event("inject_system_prompt")
        tracer.add_event("sending_to_gateway")
        await asyncio.sleep(0.1)
        tracer.add_event("response_received", {"response_length": 420})
        tracer.end_span(send_span)

        tracer.end_trace(trace_id)
        print("\n✅ OpenClaw conversation trace completed!")

    except Exception as e:
        tracer.add_event("error", {"error": str(e)})
        tracer.end_trace(trace_id)
        print(f"\n❌ OpenClaw trace failed: {e}")


async def simulate_nsfw_routing():
    """Simulate NSFW/uncensored tier routing.

    Reflects the path:
      route_and_update_config detects uncensored tier
      → config["_nsfw_mode"] = True
      → build_system_prompt injects L1B3RT4S jailbreak
    """

    print("\n" + "=" * 70)
    print("SIMULATING: NSFW/Uncensored Tier Routing")
    print("=" * 70)

    trace_id = tracer.start_trace(
        "nsfw_routing",
        attributes={
            "user_id": "123456789",
            "user_name": "TestUser",
            "message": "draw me something explicit",
        }
    )

    try:
        route_span = tracer.start_span("route_and_update_config", "openclaw")
        tracer.add_event("routing_message", {"tier": "uncensored"})
        tracer.add_attribute("routed_model", "venice/venice-uncensored-role-play")
        tracer.add_attribute("reason", "uncensored_keyword_detected")
        tracer.add_event("nsfw_mode_enabled", {"config_key": "_nsfw_mode"})
        tracer.end_span(route_span)

        agent_span = tracer.start_span("ensure_agent_exists", "openclaw")
        tracer.add_attribute("agent_id", "jennifer-user-123456789")
        tracer.add_attribute("primary_model", "venice/venice-uncensored-role-play")
        tracer.add_event("cache_miss", {"reason": "model changed to uncensored"})
        tracer.add_event("config_patched")
        tracer.end_span(agent_span)

        prompt_span = tracer.start_span("build_system_prompt", "openclaw")
        tracer.add_event("nsfw_jailbreak_injected", {"technique": "L1B3RT4S"})
        tracer.end_span(prompt_span)

        send_span = tracer.start_span("send_message", "openclaw")
        tracer.add_attribute("model_id", "venice/venice-uncensored-role-play")
        await asyncio.sleep(0.08)
        tracer.add_event("response_received")
        tracer.end_span(send_span)

        tracer.end_trace(trace_id)
        print("\n✅ NSFW routing trace completed!")

    except Exception as e:
        tracer.add_event("error", {"error": str(e)})
        tracer.end_trace(trace_id)
        print(f"\n❌ NSFW routing trace failed: {e}")


async def simulate_fallback_routing():
    """Simulate fallback chain with full provider model paths.

    After fix: fallback model paths are sent as-is (no split('/')[−1] stripping).
    e.g. "openrouter/qwen/qwen3-coder:free" stays intact.
    """

    print("\n" + "=" * 70)
    print("SIMULATING: Fallback Chain (Primary Fails → Full-Path Fallback)")
    print("=" * 70)

    trace_id = tracer.start_trace(
        "fallback_routing",
        attributes={
            "user_id": "123456789",
            "primary_model": "openai-codex/gpt-5.3-codex",
            "fallback_chain": ["kimi-coding/k2p5", "openrouter/qwen/qwen3-coder:free"],
        }
    )

    try:
        primary_span = tracer.start_span("send_primary", "openclaw")
        tracer.add_attribute("model", "openai-codex/gpt-5.3-codex")
        tracer.add_event("request_sent")
        await asyncio.sleep(0.02)
        tracer.add_event("primary_failed", {"status": 503, "model": "openai-codex/gpt-5.3-codex"})
        tracer.end_span(primary_span, SpanStatus.ERROR, "HTTP 503")

        fb1_span = tracer.start_span("send_fallback_1", "openclaw")
        tracer.add_attribute("model", "kimi-coding/k2p5")  # full path preserved
        tracer.add_event("request_sent")
        await asyncio.sleep(0.02)
        tracer.add_event("fallback_1_failed", {"status": 502, "model": "kimi-coding/k2p5"})
        tracer.end_span(fb1_span, SpanStatus.ERROR, "HTTP 502")

        fb2_span = tracer.start_span("send_fallback_2", "openclaw")
        tracer.add_attribute("model", "openrouter/qwen/qwen3-coder:free")  # :free suffix preserved
        tracer.add_event("request_sent")
        await asyncio.sleep(0.05)
        tracer.add_event("response_received", {"fallback_used": "openrouter/qwen/qwen3-coder:free"})
        tracer.end_span(fb2_span, SpanStatus.SUCCESS)

        tracer.end_trace(trace_id)
        print("\n✅ Fallback routing trace completed!")

    except Exception as e:
        tracer.add_event("error", {"error": str(e)})
        tracer.end_trace(trace_id)
        print(f"\n❌ Fallback trace failed: {e}")


async def simulate_agent_recreation():
    """Simulate !recreate agent — uses dict.pop() not set.remove()."""

    print("\n" + "=" * 70)
    print("SIMULATING: Agent Recreation (!recreate agent)")
    print("=" * 70)

    trace_id = tracer.start_trace(
        "recreate_agent",
        attributes={
            "user_id": "123456789",
            "user_name": "TestUser",
            "command": "!recreate agent",
        }
    )

    try:
        cache_span = tracer.start_span("clear_verified_cache", "openclaw")
        tracer.add_attribute("agent_id", "jennifer-user-123456789")
        # dict.pop() — safe even if key absent (was set.remove() which would crash)
        tracer.add_event("cache_popped", {"method": "_verified_agents.pop(agent_id, None)"})
        tracer.end_span(cache_span)

        delete_span = tracer.start_span("openclaw_delete_agent", "openclaw")
        tracer.add_event("deleting_agent")
        await asyncio.sleep(0.02)
        tracer.add_event("delete_failed", {"error": "agent not found in registry"})
        tracer.end_span(delete_span, SpanStatus.ERROR, "RPC error: agents.delete returned false")

        notify_span = tracer.start_span("send_error_notification", "discord")
        tracer.add_event("error_message_sent")
        tracer.end_span(notify_span)

        tracer.end_trace(trace_id)
        print("\n⚠️  Agent recreation trace completed (delete failed gracefully)!")

    except Exception as e:
        tracer.add_event("error", {"error": str(e)})
        tracer.end_trace(trace_id)
        print(f"\n❌ Agent recreation trace failed: {e}")


def main():
    """Run all trace simulations."""
    print("\n" + "=" * 70)
    print("JENNIFER BOT - END-TO-END TRACING DEMONSTRATION")
    print("=" * 70)
    print("\nCovers: image gen, model routing, NSFW tier, fallback chain, agent recreation")
    print()

    asyncio.run(simulate_discord_message())
    asyncio.run(simulate_openclaw_conversation())
    asyncio.run(simulate_nsfw_routing())
    asyncio.run(simulate_fallback_routing())
    asyncio.run(simulate_agent_recreation())

    print("\n" + "=" * 70)
    print("TRACING DEMONSTRATION COMPLETE")
    print("=" * 70)
    print("\nIn production, traces are logged as JSON for structured parsing.")
    print("Look for 'TRACE_JSON:' in the logs for complete trace data.")
    print("=" * 70)


if __name__ == "__main__":
    main()
