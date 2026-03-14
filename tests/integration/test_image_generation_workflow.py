"""
Integration tests for image generation workflow.

This module tests the full image generation workflow including:
- Configuration loading with SDBackend
- Adapter creation and usage
- Prompt formatting
- API call preparation
- Response processing
"""

import pytest
import asyncio
import base64
import io
from PIL import Image
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from pathlib import Path

from core.config import JenniferConfig, SDConfig
from integrations.image_generation import (
    create_adapter_from_config,
    PromptFormatter,
    get_backend_display_name,
)


# =============================================================================
# Configuration Integration Tests
# =============================================================================

class TestConfigurationIntegration:
    """Tests for configuration integration with image generation."""
    
    def test_sd_config_with_backend(self):
        """Test SDConfig with backend field."""
        # Test default
        sd_default = SDConfig()
        assert sd_default.backend == "automatic1111"
        
        # Test custom
        sd_comfy = SDConfig(backend="comfyui")
        assert sd_comfy.backend == "comfyui"
        
        sd_invoke = SDConfig(backend="invokeai")
        assert sd_invoke.backend == "invokeai"
    
    def test_jennifer_config_dict_access(self):
        """Test dict-style access for SDBackend."""
        config = JenniferConfig(sd=SDConfig(backend="comfyui"))
        
        # Test __getitem__
        assert config["SDBackend"] == "comfyui"
        
        # Test __contains__
        assert "SDBackend" in config
        
        # Test get() method
        assert config.get("SDBackend") == "comfyui"
    
    def test_config_migration_with_sdbackend(self):
        """Test config migration with SDBackend field."""
        # Legacy config without SDBackend
        legacy_config = {
            "Name": "TestBot",
            "SDURL": "http://localhost:7860",
            "SDmodel": "test-model",
            # No SDBackend - should default to automatic1111
        }
        
        config = JenniferConfig._migrate_legacy(legacy_config)
        assert config.sd.backend == "automatic1111"
        
        # New config with SDBackend
        new_config = {
            "Name": "TestBot",
            "SDBackend": "invokeai",
            "SDURL": "http://localhost:9090",
            "SDmodel": "test-model",
        }
        
        config = JenniferConfig._migrate_legacy(new_config)
        assert config.sd.backend == "invokeai"


# =============================================================================
# Adapter Integration Tests
# =============================================================================

class TestAdapterIntegration:
    """Tests for adapter integration with configuration."""
    
    @pytest.fixture
    def a1111_config(self):
        """Create Automatic1111 config."""
        return {
            "SDBackend": "automatic1111",
            "SDURL": "http://localhost:7860",
            "SDPositivePrompt": "masterpiece",
            "SDNegativePrompt": "low quality",
            "SDSteps": 25,
            "SDWidth": 512,
            "SDHeight": 768,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "karras",
            "SDConfig": 7.5,
            "SDmodel": "test-model",
            "SDClipSkip": 2,
        }
    
    @pytest.fixture
    def comfy_config(self):
        """Create ComfyUI config."""
        return {
            "SDBackend": "comfyui",
            "SDURL": "http://localhost:8188",
            "SDPositivePrompt": "masterpiece",
            "SDNegativePrompt": "low quality",
            "SDSteps": 30,
            "SDWidth": 512,
            "SDHeight": 512,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "normal",
            "SDConfig": 8.0,
            "SDmodel": "test-model.safetensors",
            "SDClipSkip": 1,
        }
    
    @pytest.fixture
    def invoke_config(self):
        """Create InvokeAI config."""
        return {
            "SDBackend": "invokeai",
            "SDURL": "http://localhost:9090",
            "SDPositivePrompt": "masterpiece, best quality",
            "SDNegativePrompt": "low quality",
            "SDSteps": 30,
            "SDWidth": 768,
            "SDHeight": 768,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "auto",
            "SDConfig": 7.5,
            "SDmodel": "test-model",
            "SDClipSkip": 1,
        }
    
    def test_create_adapter_from_config_automatic1111(self, a1111_config):
        """Test creating Automatic1111 adapter from config."""
        from integrations.image_generation import Automatic1111Adapter
        
        adapter = create_adapter_from_config(a1111_config)
        
        assert isinstance(adapter, Automatic1111Adapter)
        assert adapter.name == "automatic1111"
        assert adapter.get_generation_endpoint() == "http://localhost:7860/sdapi/v1/txt2img"
    
    def test_create_adapter_from_config_comfyui(self, comfy_config):
        """Test creating ComfyUI adapter from config."""
        from integrations.image_generation import ComfyUIAdapter
        
        adapter = create_adapter_from_config(comfy_config)
        
        assert isinstance(adapter, ComfyUIAdapter)
        assert adapter.name == "comfyui"
        assert adapter.get_generation_endpoint() == "http://localhost:8188/prompt"
    
    def test_create_adapter_from_config_invokeai(self, invoke_config):
        """Test creating InvokeAI adapter from config."""
        from integrations.image_generation import InvokeAIAdapter
        
        adapter = create_adapter_from_config(invoke_config)
        
        assert isinstance(adapter, InvokeAIAdapter)
        assert adapter.name == "invokeai"
        assert adapter.get_generation_endpoint() == "http://localhost:9090/api/v1/images/generate"
    
    def test_create_adapter_from_config_defaults(self):
        """Test that missing SDBackend defaults to automatic1111."""
        from integrations.image_generation import Automatic1111Adapter
        
        config = {"SDURL": "http://localhost:7860"}
        adapter = create_adapter_from_config(config)
        
        assert isinstance(adapter, Automatic1111Adapter)


# =============================================================================
# Prompt Formatter Integration Tests
# =============================================================================

class TestPromptFormatterIntegration:
    """Tests for PromptFormatter integration with adapters."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return {
            "SDBackend": "automatic1111",
            "SDURL": "http://localhost:7860",
            "SDPositivePrompt": "masterpiece, best quality",
            "SDNegativePrompt": "low quality, blurry",
            "SDSteps": 25,
            "SDWidth": 512,
            "SDHeight": 768,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "karras",
            "SDConfig": 7.5,
            "SDmodel": "test-model",
            "SDClipSkip": 2,
        }
    
    @pytest.fixture
    def formatter(self, config):
        """Create a PromptFormatter."""
        adapter = create_adapter_from_config(config)
        return PromptFormatter(adapter)
    
    def test_formatter_initialization(self, formatter):
        """Test PromptFormatter initialization."""
        assert formatter.adapter is not None
        assert formatter.adapter.name == "automatic1111"
    
    def test_format_prompt_basic(self, formatter):
        """Test basic prompt formatting."""
        payload = formatter.format_prompt("a beautiful sunset")
        
        assert payload["prompt"] == "masterpiece, best qualitya beautiful sunset"
        assert payload["steps"] == 25
        assert payload["enable_hr"] is False
    
    def test_format_prompt_with_upscale(self, formatter):
        """Test prompt formatting with upscaling."""
        payload = formatter.format_prompt("a beautiful sunset", upscale=True)
        
        assert payload["enable_hr"] is True
    
    def test_format_prompt_with_overrides(self, formatter):
        """Test prompt formatting with parameter overrides."""
        payload = formatter.format_prompt(
            "a test prompt",
            steps=50,
            width=1024,
            cfg_scale=12.0
        )
        
        assert payload["steps"] == 50
        assert payload["width"] == 1024
        assert payload["cfg_scale"] == 12.0
    
    def test_get_adapter_info(self, formatter):
        """Test getting adapter info."""
        info = formatter.get_adapter_info()
        
        assert info["name"] == "automatic1111"
        assert "generation_endpoint" in info
        assert "options_endpoint" in info
        assert "models_endpoint" in info


# =============================================================================
# Full Workflow Trace Tests
# =============================================================================

class TestFullWorkflowTrace:
    """
    Full workflow trace tests.
    
    These tests trace through the entire image generation workflow
    from configuration to API call preparation.
    """
    
    @pytest.fixture
    def full_config(self):
        """Create a complete configuration."""
        return {
            # Bot settings
            "Name": "TestJennifer",
            "Personality": "A friendly test bot",
            "DiscordToken": "test-token",
            
            # Image generation settings
            "SDBackend": "automatic1111",
            "SDURL": "http://localhost:7860",
            "SDPositivePrompt": "masterpiece, best quality, detailed",
            "SDNegativePrompt": "low quality, blurry, bad anatomy",
            "SDSteps": 30,
            "SDWidth": 512,
            "SDHeight": 768,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "karras",
            "SDConfig": 7.5,
            "SDmodel": "test-model-v1",
            "SDClipSkip": 2,
            
            # Other settings
            "OpenClawGateway": "http://localhost:8000",
            "OpenClawToken": "test-token",
            "OpenClawmodel": "test-model",
        }
    
    def test_workflow_step_1_config_loading(self, full_config):
        """
        Workflow Step 1: Configuration Loading
        
        Trace: Load config -> Validate -> Create JenniferConfig
        """
        # Load and migrate config
        config = JenniferConfig._migrate_legacy(full_config)
        
        # Verify config values
        assert config.name == "TestJennifer"
        assert config.sd.backend == "automatic1111"
        assert config.sd.url == "http://localhost:7860"
        assert config.sd.model == "test-model-v1"
        
        # Verify dict-style access
        assert config["SDBackend"] == "automatic1111"
        assert config["SDURL"] == "http://localhost:7860"
    
    def test_workflow_step_2_adapter_creation(self, full_config):
        """
        Workflow Step 2: Adapter Creation
        
        Trace: Create adapter from config -> Validate adapter type
        """
        from integrations.image_generation import Automatic1111Adapter
        
        adapter = create_adapter_from_config(full_config)
        
        # Verify adapter type
        assert isinstance(adapter, Automatic1111Adapter)
        assert adapter.name == "automatic1111"
        
        # Verify endpoints
        assert adapter.get_base_url() == "http://localhost:7860"
        assert adapter.get_generation_endpoint() == "http://localhost:7860/sdapi/v1/txt2img"
    
    def test_workflow_step_3_prompt_formatting(self, full_config):
        """
        Workflow Step 3: Prompt Formatting
        
        Trace: Create formatter -> Format prompt -> Generate payload
        """
        # Create adapter and formatter
        adapter = create_adapter_from_config(full_config)
        formatter = PromptFormatter(adapter)
        
        # Format prompt
        prompt = "a beautiful mountain landscape at sunset"
        payload = formatter.format_prompt(prompt, upscale=False)
        
        # Verify payload structure
        assert payload["prompt"] == "masterpiece, best quality, detaileda beautiful mountain landscape at sunset"
        assert payload["negative_prompt"] == "low quality, blurry, bad anatomy"
        assert payload["steps"] == 30
        assert payload["width"] == 512
        assert payload["height"] == 768
        assert payload["sampler_index"] == "DPM++ 2M"
        assert payload["scheduler"] == "karras"
        assert payload["cfg_scale"] == 7.5
        assert payload["enable_hr"] is False
        
        # Verify override settings
        assert payload["override_settings"]["sd_model_checkpoint"] == "test-model-v1"
        assert payload["override_settings"]["CLIP_stop_at_last_layers"] == 2
    
    def test_workflow_step_4_model_switching(self, full_config):
        """
        Workflow Step 4: Model Management
        
        Trace: Check current model -> Switch if needed
        """
        adapter = create_adapter_from_config(full_config)
        
        # Parse current model
        options = {"sd_model_checkpoint": "current-model"}
        current_model = adapter.parse_current_model(options)
        assert current_model == "current-model"
        
        # Create model switch payload
        switch_payload = adapter.create_model_switch_payload("new-model-v2")
        assert switch_payload == {"sd_model_checkpoint": "new-model-v2"}
    
    def test_workflow_step_5_response_processing(self, full_config):
        """
        Workflow Step 5: Response Processing
        
        Trace: Process API response -> Extract image
        """
        adapter = create_adapter_from_config(full_config)
        
        # Create test image
        test_image = Image.new('RGB', (512, 768), color='blue')
        buffered = io.BytesIO()
        test_image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        # Process response
        response = {"images": [img_base64]}
        image = adapter.process_response(response)
        
        # Verify extracted image
        assert isinstance(image, Image.Image)
        assert image.size == (512, 768)
    
    def test_workflow_step_6_models_listing(self, full_config):
        """
        Workflow Step 6: Models Listing
        
        Trace: Fetch models -> Parse list
        """
        adapter = create_adapter_from_config(full_config)
        
        # Parse models list
        models_data = [
            {"model_name": "model1"},
            {"model_name": "model2"},
            {"model_name": "model3"},
        ]
        
        models = adapter.parse_models_list(models_data)
        assert models == ["model1", "model2", "model3"]


# =============================================================================
# Backend-Specific Workflow Tests
# =============================================================================

class TestBackendSpecificWorkflows:
    """Tests for backend-specific workflow variations."""
    
    def test_automatic1111_full_workflow(self):
        """Test full workflow for Automatic1111 backend."""
        config = {
            "SDBackend": "automatic1111",
            "SDURL": "http://localhost:7860",
            "SDPositivePrompt": "masterpiece",
            "SDNegativePrompt": "low quality",
            "SDSteps": 20,
            "SDWidth": 512,
            "SDHeight": 512,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "automatic",
            "SDConfig": 7.0,
            "SDmodel": "model.ckpt",
            "SDClipSkip": 0,
        }
        
        from integrations.image_generation import Automatic1111Adapter
        
        # Create adapter
        adapter = create_adapter_from_config(config)
        assert isinstance(adapter, Automatic1111Adapter)
        
        # Format prompt
        formatter = PromptFormatter(adapter)
        payload = formatter.format_prompt("a test prompt")
        
        # Verify A1111-specific fields
        assert "sampler_index" in payload
        assert "override_settings" in payload
        assert payload["override_settings"]["sd_model_checkpoint"] == "model.ckpt"
    
    def test_comfyui_full_workflow(self):
        """Test full workflow for ComfyUI backend."""
        config = {
            "SDBackend": "comfyui",
            "SDURL": "http://localhost:8188",
            "SDPositivePrompt": "masterpiece",
            "SDNegativePrompt": "low quality",
            "SDSteps": 20,
            "SDWidth": 512,
            "SDHeight": 512,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "normal",
            "SDConfig": 7.0,
            "SDmodel": "model.safetensors",
            "SDClipSkip": 0,
        }
        
        from integrations.image_generation import ComfyUIAdapter
        
        # Create adapter
        adapter = create_adapter_from_config(config)
        assert isinstance(adapter, ComfyUIAdapter)
        
        # Format prompt
        formatter = PromptFormatter(adapter)
        payload = formatter.format_prompt("a test prompt")
        
        # Verify ComfyUI-specific fields
        assert "prompt" in payload  # Workflow
        assert "client_id" in payload
        
        workflow = payload["prompt"]
        assert any(node["class_type"] == "KSampler" for node in workflow.values())
    
    def test_invokeai_full_workflow(self):
        """Test full workflow for InvokeAI backend."""
        config = {
            "SDBackend": "invokeai",
            "SDURL": "http://localhost:9090",
            "SDPositivePrompt": "masterpiece",
            "SDNegativePrompt": "low quality",
            "SDSteps": 20,
            "SDWidth": 512,
            "SDHeight": 512,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "auto",
            "SDConfig": 7.0,
            "SDmodel": "model",
            "SDClipSkip": 0,
        }
        
        from integrations.image_generation import InvokeAIAdapter
        
        # Create adapter
        adapter = create_adapter_from_config(config)
        assert isinstance(adapter, InvokeAIAdapter)
        
        # Format prompt
        formatter = PromptFormatter(adapter)
        payload = formatter.format_prompt("a test prompt")
        
        # Verify InvokeAI-specific fields
        assert "sampler" in payload
        assert "scheduler" in payload
        # Sampler should be converted to InvokeAI format
        assert payload["sampler"] == "dpmpp_2m"


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in the image generation workflow."""
    
    def test_unknown_backend_error(self):
        """Test error handling for unknown backend."""
        config = {"SDBackend": "unknown_backend"}
        
        with pytest.raises(ValueError) as exc_info:
            create_adapter_from_config(config)
        
        assert "Unknown backend" in str(exc_info.value)
    
    def test_empty_backend_defaults_to_automatic1111(self):
        """Test that empty/missing backend defaults to automatic1111."""
        config = {"SDURL": "http://localhost:7860"}
        
        from integrations.image_generation import Automatic1111Adapter
        
        adapter = create_adapter_from_config(config)
        assert isinstance(adapter, Automatic1111Adapter)
    
    def test_process_response_error_handling(self):
        """Test error handling in response processing."""
        config = {
            "SDBackend": "automatic1111",
            "SDURL": "http://localhost:7860",
        }
        
        adapter = create_adapter_from_config(config)
        
        # Test with invalid response
        with pytest.raises(ValueError):
            adapter.process_response({"invalid": "response"})
        
        # Test with empty images
        with pytest.raises(ValueError):
            adapter.process_response({"images": []})


# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """Performance tests for the image generation workflow."""
    
    @pytest.mark.slow
    def test_adapter_creation_performance(self):
        """Test that adapter creation is fast."""
        import time
        
        config = {
            "SDBackend": "automatic1111",
            "SDURL": "http://localhost:7860",
        }
        
        # Time adapter creation
        start = time.time()
        for _ in range(1000):
            adapter = create_adapter_from_config(config)
        elapsed = time.time() - start
        
        # Should be very fast (less than 1 second for 1000 iterations)
        assert elapsed < 1.0, f"Adapter creation too slow: {elapsed:.2f}s"
    
    @pytest.mark.slow
    def test_prompt_formatting_performance(self):
        """Test that prompt formatting is fast."""
        import time
        
        config = {
            "SDBackend": "automatic1111",
            "SDURL": "http://localhost:7860",
            "SDPositivePrompt": "masterpiece, best quality, detailed, 8k uhd",
            "SDNegativePrompt": "low quality, blurry",
            "SDSteps": 30,
            "SDWidth": 512,
            "SDHeight": 768,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "karras",
            "SDConfig": 7.5,
            "SDmodel": "test-model",
            "SDClipSkip": 2,
        }
        
        adapter = create_adapter_from_config(config)
        formatter = PromptFormatter(adapter)
        
        # Time prompt formatting
        start = time.time()
        for _ in range(10000):
            payload = formatter.format_prompt("a beautiful landscape")
        elapsed = time.time() - start
        
        # Should be fast (less than 1 second for 10000 iterations)
        assert elapsed < 1.0, f"Prompt formatting too slow: {elapsed:.2f}s"
