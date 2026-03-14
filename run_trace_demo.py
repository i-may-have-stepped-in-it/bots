#!/usr/bin/env python3
"""
Run a live trace demonstration with full output visualization.
"""

import asyncio
import json
import sys
import time
sys.path.insert(0, '/app')

from core.tracing import get_tracer, SpanStatus, Tracer

# Create a fresh tracer for demo
tracer = Tracer(service_name="jennifer-demo")

def print_span_tree(trace, indent=0):
    """Print trace as a tree structure."""
    # Build parent-child relationships
    children = {}
    root_span = None
    
    for span in trace.spans:
        if span.parent_id is None:
            root_span = span
        children.setdefault(span.parent_id, []).append(span)
    
    def print_span(span, depth=0):
        prefix = "    " * depth
        duration = (span.end_time - span.start_time) * 1000 if span.end_time else 0
        status_icon = "✅" if span.status == SpanStatus.SUCCESS else "❌" if span.status == SpanStatus.ERROR else "⏳"
        
        print(f"{prefix}{status_icon} {span.name} [{span.service}] ({duration:.2f}ms)")
        
        # Print attributes
        for key, value in span.attributes.items():
            print(f"{prefix}   📋 {key}: {value}")
        
        # Print events
        for event in span.events:
            print(f"{prefix}   📍 {event['name']}")
        
        # Print children
        for child in children.get(span.id, []):
            print_span(child, depth + 1)
    
    if root_span:
        print_span(root_span)


async def simulate_full_flow():
    """Simulate a complete message-to-image flow with full tracing output."""
    
    print("\n" + "="*80)
    print("🚀 FULL END-TO-END TRACE DEMONSTRATION")
    print("="*80)
    print("\nSimulating: User sends '!draw a sunset' → Bot generates image via ComfyUI\n")
    
    # =========================================================================
    # TRACE 1: Discord Message → Image Generation
    # =========================================================================
    print("\n" + "-"*80)
    print("📨 TRACE 1: Discord Message Received")
    print("-"*80)
    
    trace_id = tracer.start_trace(
        "discord_message",
        attributes={
            "user_id": "401695424827883530",
            "user_name": "TestUser",
            "channel_id": "1226221133905268766",
            "message_id": "123456789",
            "content": "!draw a beautiful sunset over the ocean",
            "is_dm": False,
        }
    )
    
    # Message processing
    await asyncio.sleep(0.01)
    tracer.add_event("message_received", {"timestamp": time.time()})
    
    # Filter checks
    filter_span = tracer.start_span("filter_checks", "discord")
    await asyncio.sleep(0.005)
    tracer.add_event("ignored_users_check", {"passed": True})
    tracer.add_event("ignored_words_check", {"passed": True})
    tracer.add_event("channel_allowed", {"channel_id": "1226221133905268766"})
    tracer.end_span(filter_span)
    
    # Command parsing
    cmd_span = tracer.start_span("parse_command", "discord")
    tracer.add_attribute("command", "draw")
    tracer.add_attribute("args", "a beautiful sunset over the ocean")
    tracer.add_event("command_parsed")
    tracer.end_span(cmd_span)
    
    # Command handling
    handle_span = tracer.start_span("handle_draw_command", "discord")
    tracer.add_event("rate_limit_check", {"passed": True})
    tracer.add_event("queued_for_processing")
    
    # Image generation
    gen_span = tracer.start_span("generate_image", "image_gen", parent_id=handle_span)
    tracer.add_event("creating_adapter")
    tracer.add_attribute("backend", "comfyui")
    tracer.add_attribute("model", "cyberrealistic_classic40.safetensors")
    
    # ComfyUI workflow
    comfy_span = tracer.start_span("comfyui_generate", "comfyui", parent_id=gen_span)
    tracer.add_attribute("base_url", "http://josh-asus-1.tail36566.ts.net:8188")
    
    # Queue prompt
    queue_span = tracer.start_span("queue_prompt", "comfyui", parent_id=comfy_span)
    tracer.add_event("sending_post_request")
    await asyncio.sleep(0.05)  # API latency
    tracer.add_attribute("prompt_id", "uuid-abc-123-xyz")
    tracer.add_event("prompt_queued", {"prompt_id": "uuid-abc-123-xyz"})
    tracer.end_span(queue_span)
    
    # Poll for completion
    poll_span = tracer.start_span("poll_for_completion", "comfyui", parent_id=comfy_span)
    tracer.add_event("polling_started", {"max_attempts": 300})
    
    # Simulate 5 seconds of polling
    for i in range(5):
        await asyncio.sleep(0.01)
        if i == 4:
            tracer.add_event("workflow_completed", {
                "attempts": i + 1,
                "elapsed_time_ms": 5000
            })
    
    tracer.end_span(poll_span)
    
    # Fetch image
    fetch_span = tracer.start_span("fetch_image", "comfyui", parent_id=comfy_span)
    tracer.add_event("extracting_filename")
    tracer.add_attribute("filename", "ComfyUI_00001_.png")
    tracer.add_attribute("subfolder", "")
    tracer.add_event("downloading_image")
    await asyncio.sleep(0.02)
    tracer.add_event("image_downloaded", {"size_bytes": 245760})
    tracer.end_span(fetch_span)
    
    tracer.end_span(comfy_span)
    tracer.end_span(gen_span)
    
    # Send response
    response_span = tracer.start_span("send_discord_response", "discord")
    tracer.add_event("uploading_image")
    tracer.add_event("message_sent")
    tracer.end_span(response_span)
    
    tracer.end_span(handle_span)
    
    # Get trace before ending
    trace = tracer._active_traces.get(trace_id)
    
    # End trace
    tracer.end_trace(trace_id)
    
    # Print the trace tree
    print("\n📊 TRACE TREE:\n")
    if trace:
        print_span_tree(trace)
    
    # =========================================================================
    # TRACE 2: OpenClaw Conversation with per-message model routing
    # =========================================================================
    print("\n" + "-"*80)
    print("💬 TRACE 2: OpenClaw Conversation (with Model Routing)")
    print("-"*80)

    trace_id2 = tracer.start_trace(
        "openclaw_conversation",
        attributes={
            "user_id": "401695424827883530",
            "user_name": "TestUser",
            "message": "Can you help me debug this Python function?",
        }
    )

    # Model routing — runs on every message
    route_span = tracer.start_span("route_and_update_config", "openclaw")
    tracer.add_event("routing_message", {"tier": "intelligence"})
    tracer.add_attribute("routed_model", "openai-codex/gpt-5.3-codex")
    tracer.add_attribute("score", 0.75)
    tracer.add_attribute("reason", "keyword:debug complexity:medium")
    tracer.add_event("config_updated")
    tracer.end_span(route_span)

    # Agent check — _verified_agents dict keyed by agent_id -> last verified model
    agent_span = tracer.start_span("ensure_agent_exists", "openclaw")
    tracer.add_attribute("agent_id", "jennifer-user-401695424827883530")
    tracer.add_attribute("primary_model", "openai-codex/gpt-5.3-codex")
    tracer.add_event("cache_hit", {"last_verified_model": "openai-codex/gpt-5.3-codex"})
    tracer.add_event("skipped_rpc", {"reason": "model unchanged since last message"})
    tracer.end_span(agent_span)

    # Send message — full model path, no prefix stripping
    send_span = tracer.start_span("send_message", "openclaw")
    tracer.add_attribute("model_id", "openai-codex/gpt-5.3-codex")
    tracer.add_event("inject_system_prompt")
    tracer.add_event("sending_to_gateway")
    await asyncio.sleep(0.15)
    tracer.add_event("response_received", {"response_length": 420})
    tracer.end_span(send_span)

    discord_span = tracer.start_span("send_discord_message", "discord")
    tracer.add_event("message_sent")
    tracer.end_span(discord_span)

    trace2 = tracer._active_traces.get(trace_id2)
    tracer.end_trace(trace_id2)

    print("\n📊 TRACE TREE:\n")
    if trace2:
        print_span_tree(trace2)

    # =========================================================================
    # TRACE 3: NSFW Tier Routing
    # =========================================================================
    print("\n" + "-"*80)
    print("🔞 TRACE 3: NSFW/Uncensored Tier Routing")
    print("-"*80)

    trace_id3 = tracer.start_trace(
        "nsfw_routing",
        attributes={
            "user_id": "401695424827883530",
            "user_name": "TestUser",
            "message": "draw me something explicit",
        }
    )

    route_span3 = tracer.start_span("route_and_update_config", "openclaw")
    tracer.add_event("routing_message", {"tier": "uncensored"})
    tracer.add_attribute("routed_model", "venice/venice-uncensored-role-play")
    tracer.add_attribute("reason", "uncensored_keyword_detected")
    tracer.add_event("nsfw_mode_enabled", {"config_key": "_nsfw_mode"})
    tracer.end_span(route_span3)

    agent_span3 = tracer.start_span("ensure_agent_exists", "openclaw")
    tracer.add_attribute("primary_model", "venice/venice-uncensored-role-play")
    tracer.add_event("cache_miss", {"reason": "model changed to uncensored tier"})
    tracer.add_event("config_patched")
    tracer.end_span(agent_span3)

    prompt_span3 = tracer.start_span("build_system_prompt", "openclaw")
    tracer.add_event("nsfw_jailbreak_injected", {"technique": "L1B3RT4S"})
    tracer.end_span(prompt_span3)

    send_span3 = tracer.start_span("send_message", "openclaw")
    tracer.add_attribute("model_id", "venice/venice-uncensored-role-play")
    await asyncio.sleep(0.08)
    tracer.add_event("response_received")
    tracer.end_span(send_span3)

    trace3 = tracer._active_traces.get(trace_id3)
    tracer.end_trace(trace_id3)

    print("\n📊 TRACE TREE:\n")
    if trace3:
        print_span_tree(trace3)

    # =========================================================================
    # TRACE 4: Fallback Chain (full provider paths preserved)
    # =========================================================================
    print("\n" + "-"*80)
    print("🔄 TRACE 4: Fallback Chain (Primary → Fallback)")
    print("-"*80)

    trace_id4 = tracer.start_trace(
        "fallback_routing",
        attributes={
            "user_id": "401695424827883530",
            "primary_model": "openai-codex/gpt-5.3-codex",
            "fallback_chain": ["kimi-coding/k2p5", "openrouter/qwen/qwen3-coder:free"],
        }
    )

    primary_span = tracer.start_span("send_primary", "openclaw")
    tracer.add_attribute("model", "openai-codex/gpt-5.3-codex")
    await asyncio.sleep(0.02)
    tracer.add_event("primary_failed", {"status": 503})
    tracer.end_span(primary_span, SpanStatus.ERROR, "HTTP 503")

    fb_span = tracer.start_span("send_fallback", "openclaw")
    # Full model path preserved — no split("/")[-1] stripping
    tracer.add_attribute("model", "openrouter/qwen/qwen3-coder:free")
    await asyncio.sleep(0.05)
    tracer.add_event("response_received", {"fallback_used": "openrouter/qwen/qwen3-coder:free"})
    tracer.end_span(fb_span, SpanStatus.SUCCESS)

    trace4 = tracer._active_traces.get(trace_id4)
    tracer.end_trace(trace_id4)

    print("\n📊 TRACE TREE:\n")
    if trace4:
        print_span_tree(trace4)

    # =========================================================================
    # TRACE 5: Agent Recreation (dict.pop cache invalidation)
    # =========================================================================
    print("\n" + "-"*80)
    print("❌ TRACE 5: Agent Recreation (!recreate agent)")
    print("-"*80)

    trace_id5 = tracer.start_trace(
        "recreate_agent",
        attributes={
            "user_id": "401695424827883530",
            "user_name": "TestUser",
            "command": "!recreate agent",
        }
    )

    cache_span = tracer.start_span("clear_verified_cache", "openclaw")
    tracer.add_attribute("agent_id", "jennifer-user-401695424827883530")
    tracer.add_event("cache_popped", {"method": "_verified_agents.pop(agent_id, None)"})
    tracer.end_span(cache_span)

    delete_span = tracer.start_span("delete_openclaw_agent", "openclaw")
    tracer.add_event("deleting_agent")
    await asyncio.sleep(0.02)
    tracer.add_event("delete_failed", {"error": "agent not found in registry"})
    tracer.end_span(delete_span, SpanStatus.ERROR, "RPC error: agents.delete returned false")

    notify_span = tracer.start_span("send_error_notification", "discord")
    tracer.add_event("error_message_sent")
    tracer.end_span(notify_span)

    trace5 = tracer._active_traces.get(trace_id5)
    tracer.end_trace(trace_id5)

    print("\n📊 TRACE TREE:\n")
    if trace5:
        print_span_tree(trace5)

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "="*80)
    print("📈 TRACE SUMMARY")
    print("="*80)

    all_traces = [
        ("Discord → Image Gen", trace),
        ("OpenClaw Chat + Routing", trace2),
        ("NSFW Tier Routing", trace3),
        ("Fallback Chain", trace4),
        ("Agent Recreate (Error)", trace5),
    ]
    
    for name, t in all_traces:
        if t:
            duration = (t.end_time - t.start_time) * 1000 if t.end_time else 0
            services = set(s.service for s in t.spans)
            errors = sum(1 for s in t.spans if s.error)
            
            print(f"\n{name}:")
            print(f"  Duration: {duration:.2f}ms")
            print(f"  Services: {', '.join(services)}")
            print(f"  Spans: {len(t.spans)}")
            print(f"  Errors: {errors}")
    
    # Show JSON output example
    print("\n" + "="*80)
    print("📄 STRUCTURED JSON OUTPUT (for log parsing)")
    print("="*80)
    
    if trace:
        json_output = json.dumps(trace.to_dict(), indent=2, default=str)
        # Truncate for display
        lines = json_output.split('\n')[:30]
        print('\n'.join(lines))
        print("... (truncated)")
    
    print("\n" + "="*80)
    print("✅ TRACE DEMONSTRATION COMPLETE")
    print("="*80)
    print("\n💡 To see live traces in production:")
    print("   docker logs jennifer 2>&1 | grep 'TRACE_JSON'")
    print("\n💡 To see human-readable summaries:")
    print("   docker logs jennifer 2>&1 | grep 'TRACE COMPLETED'")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(simulate_full_flow())
