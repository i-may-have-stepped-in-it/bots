"""
Tests for image generation adapters.

This module tests the adapter pattern implementation for different
Stable Diffusion backends (Automatic1111, ComfyUI, InvokeAI).
"""

import pytest
import base64
import io
from PIL import Image
from unittest.mock import MagicMock, patch

from integrations.image_generation import (
    BaseImageAdapter,
    Automatic1111Adapter,
    ComfyUIAdapter,
    InvokeAIAdapter,
    create_adapter,
    get_available_adapters,
    is_backend_supported,
    get_backend_display_name,
)


# =============================================================================
# Adapter Factory Tests
# =============================================================================

class TestAdapterFactory:
    """Tests for the adapter factory functions."""
    
    def test_get_available_adapters(self):
        """Test that all expected adapters are available."""
        adapters = get_available_adapters()
        
        # Check that main backends are available
        assert "automatic1111" in adapters
        assert "comfyui" in adapters
        assert "invokeai" in adapters
        
        # Check that aliases exist
        assert "auto" in adapters
        assert "a1111" in adapters
        assert "comfy" in adapters
        assert "invoke" in adapters
    
    def test_is_backend_supported(self):
        """Test backend support checking."""
        assert is_backend_supported("automatic1111") is True
        assert is_backend_supported("comfyui") is True
        assert is_backend_supported("invokeai") is True
        assert is_backend_supported("auto") is True  # Alias
        
        assert is_backend_supported("unknown") is False
        assert is_backend_supported("") is False
    
    def test_get_backend_display_name(self):
        """Test backend display name generation."""
        assert get_backend_display_name("automatic1111") == "Automatic1111 WebUI"
        assert get_backend_display_name("comfyui") == "ComfyUI"
        assert get_backend_display_name("invokeai") == "InvokeAI"
        assert get_backend_display_name("unknown") == "unknown"
    
    def test_create_adapter_automatic1111(self):
        """Test creating Automatic1111 adapter."""
        config = {"SDURL": "http://localhost:7860", "SDmodel": "test-model"}
        adapter = create_adapter("automatic1111", config)
        
        assert isinstance(adapter, Automatic1111Adapter)
        assert adapter.name == "automatic1111"
        assert adapter.config == config
    
    def test_create_adapter_comfyui(self):
        """Test creating ComfyUI adapter."""
        config = {"SDURL": "http://localhost:8188", "SDmodel": "test-model"}
        adapter = create_adapter("comfyui", config)
        
        assert isinstance(adapter, ComfyUIAdapter)
        assert adapter.name == "comfyui"
        assert adapter.config == config
    
    def test_create_adapter_invokeai(self):
        """Test creating InvokeAI adapter."""
        config = {"SDURL": "http://localhost:9090", "SDmodel": "test-model"}
        adapter = create_adapter("invokeai", config)
        
        assert isinstance(adapter, InvokeAIAdapter)
        assert adapter.name == "invokeai"
        assert adapter.config == config
    
    def test_create_adapter_with_aliases(self):
        """Test creating adapters with aliases."""
        config = {"SDURL": "http://localhost:7860"}
        
        # All these should create Automatic1111 adapters
        a1111_aliases = ["automatic1111", "auto", "a1111", "webui"]
        for alias in a1111_aliases:
            adapter = create_adapter(alias, config)
            assert isinstance(adapter, Automatic1111Adapter), f"Failed for alias: {alias}"
    
    def test_create_adapter_unknown_backend(self):
        """Test that unknown backends raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            create_adapter("unknown_backend", {})
        
        assert "Unknown backend" in str(exc_info.value)


# =============================================================================
# Automatic1111 Adapter Tests
# =============================================================================

class TestAutomatic1111Adapter:
    """Tests for the Automatic1111 adapter."""
    
    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return {
            "SDURL": "http://localhost:7860",
            "SDPositivePrompt": "masterpiece, best quality",
            "SDNegativePrompt": "low quality, blurry",
            "SDSteps": 25,
            "SDWidth": 512,
            "SDHeight": 768,
            "SDSampler": "DPM++ 2M",
            "SDScheduler": "karras",
            "SDConfig": 7.5,
            "SDmodel": "test-model-v1",
            "SDClipSkip": 2,
        }
    
    @pytest.fixture
    def adapter(self, config):
        """Create an Automatic1111 adapter."""
        return Automatic1111Adapter(config)
    
    def test_name_property(self, adapter):
        """Test adapter name."""
        assert adapter.name == "automatic1111"
    
    def test_get_base_url(self, adapter):
        """Test base URL retrieval."""
        assert adapter.get_base_url() == "http://localhost:7860"
    
    def test_get_generation_endpoint(self, adapter):
        """Test generation endpoint."""
        assert adapter.get_generation_endpoint() == "http://localhost:7860/sdapi/v1/txt2img"
    
    def test_get_options_endpoint(self, adapter):
        """Test options endpoint."""
        assert adapter.get_options_endpoint() == "http://localhost:7860/sdapi/v1/options"
    
    def test_get_models_endpoint(self, adapter):
        """Test models endpoint."""
        assert adapter.get_models_endpoint() == "http://localhost:7860/sdapi/v1/sd-models"
    
    def test_get_refresh_models_endpoint(self, adapter):
        """Test refresh models endpoint."""
        assert adapter.get_refresh_models_endpoint() == "http://localhost:7860/sdapi/v1/refresh-checkpoints"
    
    def test_prepare_payload_basic(self, adapter):
        """Test basic payload preparation."""
        payload = adapter.prepare_payload("a beautiful sunset")
        
        assert payload["prompt"] == "masterpiece, best qualitya beautiful sunset"
        assert payload["steps"] == 25
        assert payload["width"] == 512
        assert payload["height"] == 768
        assert payload["negative_prompt"] == "low quality, blurry"
        assert payload["sampler_index"] == "DPM++ 2M"
        assert payload["scheduler"] == "karras"
        assert payload["cfg_scale"] == 7.5
        assert payload["enable_hr"] is False
        
        # Check override settings
        assert payload["override_settings"]["sd_model_checkpoint"] == "test-model-v1"
        assert payload["override_settings"]["CLIP_stop_at_last_layers"] == 2
    
    def test_prepare_payload_with_upscale(self, adapter):
        """Test payload preparation with upscaling."""
        payload = adapter.prepare_payload("a beautiful sunset", upscale=True)
        
        assert payload["enable_hr"] is True
        assert payload["hr_upscaler"] == "R-ESRGAN 4x+"
        assert payload["denoising_strength"] == 0.5
    
    def test_prepare_payload_with_kwargs(self, adapter):
        """Test payload preparation with override kwargs."""
        payload = adapter.prepare_payload(
            "a test prompt",
            steps=50,
            width=1024,
            height=1024,
            cfg_scale=12.0,
            model="custom-model"
        )
        
        assert payload["steps"] == 50
        assert payload["width"] == 1024
        assert payload["height"] == 1024
        assert payload["cfg_scale"] == 12.0
        assert payload["override_settings"]["sd_model_checkpoint"] == "custom-model"
    
    def test_prepare_payload_with_list_prompt(self, adapter):
        """Test payload preparation with list prompt."""
        payload = adapter.prepare_payload(["part1", "part2", "part3"])
        
        assert payload["prompt"] == "masterpiece, best qualitypart1 part2 part3"
    
    def test_process_response_success(self, adapter):
        """Test successful response processing."""
        # Create a test image
        test_image = Image.new('RGB', (512, 768), color='red')
        buffered = io.BytesIO()
        test_image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        response = {"images": [img_base64]}
        image = adapter.process_response(response)
        
        assert isinstance(image, Image.Image)
        assert image.size == (512, 768)
    
    def test_process_response_no_images(self, adapter):
        """Test response processing with no images."""
        with pytest.raises(ValueError) as exc_info:
            adapter.process_response({})
        
        assert "No images found" in str(exc_info.value)
    
    def test_process_response_empty_images(self, adapter):
        """Test response processing with empty images array."""
        with pytest.raises(ValueError) as exc_info:
            adapter.process_response({"images": []})
        
        assert "No images found" in str(exc_info.value)
    
    def test_parse_current_model(self, adapter):
        """Test parsing current model from options."""
        options = {"sd_model_checkpoint": "current-model-v2"}
        model = adapter.parse_current_model(options)
        
        assert model == "current-model-v2"
    
    def test_parse_current_model_not_found(self, adapter):
        """Test parsing current model when not present."""
        options = {"other_setting": "value"}
        model = adapter.parse_current_model(options)
        
        assert model is None
    
    def test_create_model_switch_payload(self, adapter):
        """Test model switch payload creation."""
        payload = adapter.create_model_switch_payload("new-model-v3")
        
        assert payload == {"sd_model_checkpoint": "new-model-v3"}
    
    def test_parse_models_list(self, adapter):
        """Test parsing models list."""
        models_data = [
            {"model_name": "model1", "title": "Model 1"},
            {"model_name": "model2", "title": "Model 2"},
            {"model_name": "", "title": "Empty Model"},  # Should be filtered
        ]
        
        models = adapter.parse_models_list(models_data)
        
        assert models == ["model1", "model2"]
    
    def test_parse_models_list_empty(self, adapter):
        """Test parsing empty models list."""
        assert adapter.parse_models_list([]) == []
        assert adapter.parse_models_list(None) == []


# =============================================================================
# ComfyUI Adapter Tests
# =============================================================================

class TestComfyUIAdapter:
    """Tests for the ComfyUI adapter."""
    
    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return {
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
    def adapter(self, config):
        """Create a ComfyUI adapter."""
        return ComfyUIAdapter(config)
    
    def test_name_property(self, adapter):
        """Test adapter name."""
        assert adapter.name == "comfyui"
    
    def test_get_generation_endpoint(self, adapter):
        """Test generation endpoint."""
        assert adapter.get_generation_endpoint() == "http://localhost:8188/prompt"
    
    def test_get_options_endpoint(self, adapter):
        """Test options endpoint."""
        assert adapter.get_options_endpoint() == "http://localhost:8188/system_stats"
    
    def test_get_models_endpoint(self, adapter):
        """Test models endpoint."""
        assert adapter.get_models_endpoint() == "http://localhost:8188/object_info/CheckpointLoaderSimple"
    
    def test_get_refresh_models_endpoint(self, adapter):
        """Test that ComfyUI doesn't have refresh endpoint."""
        assert adapter.get_refresh_models_endpoint() is None
    
    def test_prepare_payload_structure(self, adapter):
        """Test ComfyUI payload structure."""
        payload = adapter.prepare_payload("a test prompt")
        
        # ComfyUI uses a workflow structure
        assert "prompt" in payload
        assert "client_id" in payload
        
        workflow = payload["prompt"]
        
        # Check for expected node types
        node_classes = [node["class_type"] for node in workflow.values()]
        assert "CheckpointLoaderSimple" in node_classes
        assert "CLIPTextEncode" in node_classes
        assert "EmptyLatentImage" in node_classes
        assert "KSampler" in node_classes
        assert "VAEDecode" in node_classes
        assert "SaveImage" in node_classes
    
    def test_prepare_prompt_in_workflow(self, adapter):
        """Test that prompt is correctly embedded in workflow."""
        payload = adapter.prepare_payload("beautiful landscape")
        
        workflow = payload["prompt"]
        
        # Find the positive prompt node
        positive_nodes = [
            node for node in workflow.values()
            if node["class_type"] == "CLIPTextEncode" and 
            "masterpiece" in node["inputs"].get("text", "")
        ]
        
        assert len(positive_nodes) > 0
        assert any("beautiful landscape" in node["inputs"]["text"] for node in positive_nodes)
    
    def test_parse_current_model(self, adapter):
        """Test that ComfyUI returns None for current model."""
        # ComfyUI doesn't have a global current model
        assert adapter.parse_current_model({}) is None
        assert adapter.parse_current_model({"some": "data"}) is None
    
    def test_create_model_switch_payload(self, adapter):
        """Test that ComfyUI returns empty model switch payload."""
        # ComfyUI doesn't support global model switching
        assert adapter.create_model_switch_payload("any-model") == {}
    
    def test_get_history_endpoint(self, adapter):
        """Test history endpoint generation."""
        endpoint = adapter.get_history_endpoint("test-prompt-id-123")
        assert endpoint == "http://localhost:8188/history/test-prompt-id-123"
    
    def test_get_image_endpoint(self, adapter):
        """Test image endpoint generation."""
        endpoint = adapter.get_image_endpoint("image.png", "output", "output")
        assert "filename=image.png" in endpoint
        assert "subfolder=output" in endpoint
        assert "type=output" in endpoint
    
    def test_parse_models_list(self, adapter):
        """Test parsing ComfyUI models list."""
        # ComfyUI returns models in object_info format
        models_data = {
            "CheckpointLoaderSimple": {
                "input": {
                    "required": {
                        "ckpt_name": [
                            ["model1.safetensors", "model2.ckpt", "model3.safetensors"]
                        ]
                    }
                }
            }
        }
        
        models = adapter.parse_models_list(models_data)
        assert models == ["model1.safetensors", "model2.ckpt", "model3.safetensors"]
    
    def test_parse_models_list_invalid(self, adapter):
        """Test parsing invalid ComfyUI models data."""
        assert adapter.parse_models_list({}) == []
        assert adapter.parse_models_list(None) == []
        assert adapter.parse_models_list(["invalid"]) == []


# =============================================================================
# InvokeAI Adapter Tests
# =============================================================================

class TestInvokeAIAdapter:
    """Tests for the InvokeAI adapter."""
    
    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return {
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
    
    @pytest.fixture
    def adapter(self, config):
        """Create an InvokeAI adapter."""
        return InvokeAIAdapter(config)
    
    def test_name_property(self, adapter):
        """Test adapter name."""
        assert adapter.name == "invokeai"
    
    def test_get_generation_endpoint(self, adapter):
        """Test generation endpoint."""
        assert adapter.get_generation_endpoint() == "http://localhost:9090/api/v1/images/generate"
    
    def test_get_options_endpoint(self, adapter):
        """Test options endpoint."""
        assert adapter.get_options_endpoint() == "http://localhost:9090/api/v1/app/config"
    
    def test_get_models_endpoint(self, adapter):
        """Test models endpoint."""
        assert adapter.get_models_endpoint() == "http://localhost:9090/api/v1/models/"
    
    def test_get_refresh_models_endpoint(self, adapter):
        """Test that InvokeAI doesn't have explicit refresh endpoint."""
        assert adapter.get_refresh_models_endpoint() is None
    
    def test_prepare_payload_basic(self, adapter):
        """Test basic payload preparation."""
        payload = adapter.prepare_payload("a beautiful portrait")
        
        assert payload["prompt"] == "masterpiece, best qualitya beautiful portrait"
        assert payload["negative_prompt"] == "low quality"
        assert payload["width"] == 768
        assert payload["height"] == 768
        assert payload["steps"] == 30
        assert payload["cfg_scale"] == 7.5
        assert payload["model"] == "test-model"
        assert payload["clip_skip"] == 1
        assert "seed" in payload
    
    def test_prepare_payload_sampler_conversion(self, adapter):
        """Test sampler name conversion."""
        # Test sampler conversion from A1111 format to InvokeAI format
        assert adapter._convert_sampler("DPM++ 2M") == "dpmpp_2m"
        assert adapter._convert_sampler("Euler a") == "euler_ancestral"
        assert adapter._convert_sampler("DDIM") == "ddim"
        assert adapter._convert_sampler("Unknown") == "unknown"
    
    def test_prepare_payload_scheduler_conversion(self, adapter):
        """Test scheduler name conversion."""
        assert adapter._convert_scheduler("automatic") == "auto"
        assert adapter._convert_scheduler("karras") == "karras"
        assert adapter._convert_scheduler("uniform") == "normal"
        assert adapter._convert_scheduler("exponential") == "exponential"
    
    def test_prepare_payload_with_upscale(self, adapter):
        """Test payload with upscaling."""
        payload = adapter.prepare_payload("test", upscale=True)
        
        assert "high_resolution" in payload
        assert payload["high_resolution"]["scale"] == 2.0
    
    def test_process_response_with_items(self, adapter):
        """Test processing response with items array."""
        # Create test image
        test_image = Image.new('RGB', (512, 512), color='blue')
        buffered = io.BytesIO()
        test_image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        response = {
            "items": [
                {"image": img_base64, "seed": 12345}
            ]
        }
        
        image = adapter.process_response(response)
        assert isinstance(image, Image.Image)
    
    def test_process_response_direct_image(self, adapter):
        """Test processing response with direct image field."""
        test_image = Image.new('RGB', (512, 512), color='green')
        buffered = io.BytesIO()
        test_image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        response = {"image": img_base64}
        
        image = adapter.process_response(response)
        assert isinstance(image, Image.Image)
    
    def test_process_response_images_array(self, adapter):
        """Test processing response with images array."""
        test_image = Image.new('RGB', (512, 512), color='red')
        buffered = io.BytesIO()
        test_image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        response = {"images": [img_base64]}
        
        image = adapter.process_response(response)
        assert isinstance(image, Image.Image)
    
    def test_process_response_unknown_format(self, adapter):
        """Test processing unknown response format."""
        with pytest.raises(ValueError) as exc_info:
            adapter.process_response({"unknown": "format"})
        
        assert "Unexpected InvokeAI response format" in str(exc_info.value)
    
    def test_parse_current_model(self, adapter):
        """Test parsing current model from config."""
        options = {"model": {"model_name": "current-model"}}
        model = adapter.parse_current_model(options)
        
        assert model == "current-model"
    
    def test_parse_current_model_alternative_format(self, adapter):
        """Test parsing current model from alternative format."""
        options = {
            "models": {
                "main": {"model_name": "main-model"}
            }
        }
        model = adapter.parse_current_model(options)
        
        assert model == "main-model"
    
    def test_parse_current_model_not_found(self, adapter):
        """Test parsing when model not found."""
        assert adapter.parse_current_model({}) is None
    
    def test_create_model_switch_payload(self, adapter):
        """Test model switch payload creation."""
        # InvokeAI has limited model switching support
        payload = adapter.create_model_switch_payload("new-model")
        assert payload == {"model_name": "new-model"}
    
    def test_parse_models_list_direct(self, adapter):
        """Test parsing direct models list."""
        models_data = [
            {"model_name": "model1", "base_model": "sdxl"},
            {"model_name": "model2", "base_model": "sd1.5"},
        ]
        
        models = adapter.parse_models_list(models_data)
        assert models == ["model1", "model2"]
    
    def test_parse_models_list_with_items(self, adapter):
        """Test parsing models list with items wrapper."""
        models_data = {
            "items": [
                {"name": "model1"},
                {"name": "model2"},
            ]
        }
        
        models = adapter.parse_models_list(models_data)
        assert models == ["model1", "model2"]
    
    def test_parse_models_list_with_models_key(self, adapter):
        """Test parsing models list with models key."""
        models_data = {
            "models": [
                {"model_name": "model1"},
                {"model_name": "model2"},
            ]
        }
        
        models = adapter.parse_models_list(models_data)
        assert models == ["model1", "model2"]
    
    def test_get_queue_endpoint(self, adapter):
        """Test queue endpoint."""
        assert adapter.get_queue_endpoint() == "http://localhost:9090/api/v1/queue/default/enqueue_batch"
    
    def test_get_sessions_endpoint(self, adapter):
        """Test sessions endpoint."""
        assert adapter.get_sessions_endpoint() == "http://localhost:9090/api/v1/sessions"
    
    def test_get_session_status_endpoint(self, adapter):
        """Test session status endpoint."""
        endpoint = adapter.get_session_status_endpoint("session-123")
        assert endpoint == "http://localhost:9090/api/v1/sessions/session-123"


# =============================================================================
# Base Adapter Abstract Class Tests
# =============================================================================

class TestBaseAdapter:
    """Tests for the base adapter abstract class."""
    
    def test_base_adapter_is_abstract(self):
        """Test that BaseImageAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseImageAdapter({})
    
    def test_concrete_adapter_implements_interface(self):
        """Test that concrete adapters implement all abstract methods."""
        config = {"SDURL": "http://test"}
        
        # All these should work without raising
        a1111 = Automatic1111Adapter(config)
        comfy = ComfyUIAdapter(config)
        invoke = InvokeAIAdapter(config)
        
        # Check that they have all required methods
        for adapter in [a1111, comfy, invoke]:
            assert hasattr(adapter, 'name')
            assert hasattr(adapter, 'prepare_payload')
            assert hasattr(adapter, 'get_generation_endpoint')
            assert hasattr(adapter, 'process_response')
            assert hasattr(adapter, 'get_options_endpoint')
            assert hasattr(adapter, 'get_models_endpoint')
            assert hasattr(adapter, 'parse_current_model')
            assert hasattr(adapter, 'create_model_switch_payload')
            assert hasattr(adapter, 'parse_models_list')
