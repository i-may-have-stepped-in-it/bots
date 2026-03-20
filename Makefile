# Makefile for Jennifer Discord Bot
.PHONY: help install install-dev test test-unit test-cov test-all lint format clean \
        docker-build docker-up docker-down \
        sd-a111 sd-comfy sd-invoke \
        sd-a111-cpu sd-comfy-cpu sd-invoke-cpu \
        all up stop logs status switch

# Default target
help:
	@echo "Jennifer Discord Bot - Available Commands:"
	@echo ""
	@echo "Setup:"
	@echo "  install        Install production dependencies"
	@echo "  install-dev    Install development dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  test           Run unit tests quickly"
	@echo "  test-unit      Run all unit tests"
	@echo "  test-cov       Run tests with coverage report"
	@echo "  test-all       Run all tests including integration"
	@echo "  test-ci        Run tests for CI (with coverage)"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint           Run linting (flake8)"
	@echo "  format         Format code with black"
	@echo "  format-check   Check code formatting"
	@echo "  typecheck      Run type checking (mypy)"
	@echo ""
	@echo "Docker - Stable Diffusion Backends (NVIDIA GPU):"
	@echo "  sd-a111        Start with Automatic1111 (GPU)"
	@echo "  sd-comfy       Start with ComfyUI (GPU)"
	@echo "  sd-invoke      Start with InvokeAI (GPU)"
	@echo ""
	@echo "Docker - Stable Diffusion Backends (CPU):"
	@echo "  sd-a111-cpu    Start with Automatic1111 (CPU)"
	@echo "  sd-comfy-cpu   Start with ComfyUI (CPU)"
	@echo "  sd-invoke-cpu  Start with InvokeAI (CPU)"
	@echo ""
	@echo "Docker - Full Stack:"
	@echo "  all            Start full stack (A1111 + LLM NVIDIA)"
	@echo "  up             Start with current config"
	@echo "  stop           Stop all services"
	@echo "  logs           View bot logs"
	@echo "  status         Show running containers"
	@echo ""
	@echo "Docker - Switch Backend:"
	@echo "  switch BACKEND=comfyui GPU=nvidia   Switch SD backend"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean          Remove cache files and temporary directories"
	@echo "  clean-all      Deep clean including virtual environment"

# Setup
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

# Testing
test:
	pytest tests/unit -v --tb=short -m "not slow" --timeout=60

test-unit:
	pytest tests/unit -v --tb=short

test-cov:
	pytest tests/unit -v --tb=short --cov=core --cov=utils --cov=bot --cov-report=term-missing --cov-report=html

test-all:
	pytest -v --tb=short --cov=core --cov=utils --cov=bot --cov-report=term-missing

test-ci:
	pytest --cov=core --cov=utils --cov=bot --cov-report=xml --cov-report=term -v --tb=short --timeout=60

# Code Quality
lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=venv,__pycache__,.git,data,logs
	flake8 . --count --exit-zero --max-complexity=10 --max-line-length=100 --statistics --exclude=venv,__pycache__,.git,data,logs

format:
	black --exclude='venv|__pycache__|data|logs' .
	isort --skip-glob='venv' --skip='data' --skip='logs' .

format-check:
	black --check --diff --exclude='venv|__pycache__|data|logs' .

typecheck:
	mypy core utils bot --ignore-missing-imports --exclude='venv|data|logs'

# Docker
docker-build:
	docker-compose -f docker-compose-jennifer.yml build jennifer

docker-up:
	docker-compose -f docker-compose-jennifer.yml up -d

docker-down:
	docker-compose -f docker-compose-jennifer.yml down

# Stable Diffusion Backends - NVIDIA GPU
sd-a111:
	docker-compose -f docker-compose-jennifer.yml --profile sd-a1111-nvidia --profile llm-nvidia up -d

sd-comfy:
	docker-compose -f docker-compose-jennifer.yml --profile sd-comfyui-nvidia --profile llm-nvidia up -d

sd-invoke:
	docker-compose -f docker-compose-jennifer.yml --profile sd-invokeai-nvidia --profile llm-nvidia up -d

# Stable Diffusion Backends - CPU
sd-a111-cpu:
	docker-compose -f docker-compose-jennifer.yml --profile sd-a1111-cpu --profile llm-cpu up -d

sd-comfy-cpu:
	docker-compose -f docker-compose-jennifer.yml --profile sd-comfyui-cpu --profile llm-cpu up -d

sd-invoke-cpu:
	docker-compose -f docker-compose-jennifer.yml --profile sd-invokeai-cpu --profile llm-cpu up -d

# Full Stack
all:
	docker-compose -f docker-compose-jennifer.yml --profile all up -d

up:
	docker-compose -f docker-compose-jennifer.yml up -d

stop:
	docker-compose -f docker-compose-jennifer.yml down

logs:
	docker logs -f jennifer

status:
	docker ps --filter "name=jennifer" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Switch Backend (usage: make switch BACKEND=comfyui GPU=nvidia)
BACKEND ?= comfyui
GPU ?= nvidia
switch:
	./scripts/switch-sd-backend.sh $(BACKEND) $(GPU)

# Maintenance
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .mypy_cache 2>/dev/null || true
	rm -rf tests/temp/* 2>/dev/null || true

clean-all: clean
	rm -rf venv 2>/dev/null || true
	rm -rf data/*.db logs/*.log 2>/dev/null || true
