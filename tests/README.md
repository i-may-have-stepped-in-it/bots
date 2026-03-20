# Jennifer Bot Test Suite

This directory contains the complete test suite for the Jennifer Discord bot.

## Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Shared pytest fixtures and configuration
├── pytest.ini               # pytest configuration
├── README.md                # This file
├── fixtures/                # Test fixtures and mocks
│   ├── __init__.py
│   ├── discord_mocks.py     # Discord.py mock objects
│   └── config_fixtures.py   # Configuration fixtures
├── unit/                    # Unit tests
│   ├── core/               # Core module tests
│   │   ├── test_config.py
│   │   ├── test_logging_config.py
│   │   └── test_persistent_queue.py
│   ├── utils/              # Utility tests
│   │   └── test_model_router.py
│   └── bot/                # Bot tests
│       └── test_handlers.py
└── integration/            # Integration tests
    └── (integration tests)
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run unit tests only
```bash
pytest tests/unit -v
```

### Run with coverage
```bash
pytest --cov=core --cov=utils --cov=bot --cov-report=term-missing
```

### Run specific test file
```bash
pytest tests/unit/core/test_config.py -v
```

### Run tests matching a pattern
```bash
pytest -k "test_config" -v
```

### Run tests excluding slow tests
```bash
pytest -m "not slow" -v
```

### Run tests with specific markers
```bash
pytest -m "config" -v
pytest -m "queue" -v
```

## Test Markers

- `@pytest.mark.slow` - Slow tests (excluded from quick runs)
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.discord` - Tests requiring discord.py
- `@pytest.mark.config` - Configuration-related tests
- `@pytest.mark.queue` - Queue-related tests
- `@pytest.mark.unit` - Unit tests

## Fixtures

### Configuration Fixtures

- `minimal_config_dict` - Minimal valid configuration
- `full_config_dict` - Full configuration with all options
- `legacy_config_dict` - Legacy config for migration testing
- `config_file` - Path to temporary config file

### Discord Mock Fixtures

- `mock_discord_message` - Mock Discord message
- `mock_discord_dm` - Mock DM message
- `mock_discord_user` - Mock Discord user
- `mock_discord_bot_user` - Mock bot user
- `mock_voice_channel` - Mock voice channel
- `mock_member_with_voice` - Mock member in voice channel
- `mock_admin_member` - Mock admin member

### Queue Fixtures

- `temp_queue` - Temporary PersistentQueue instance
- `temp_task_manager` - Temporary TaskManager instance
- `sample_task_payload` - Sample task payload dict

### Directory Fixtures

- `temp_dir` - Temporary directory
- `temp_data_dir` - Temporary data directory
- `temp_config_dir` - Temporary config directory
- `temp_logs_dir` - Temporary logs directory

## Writing Tests

### Basic Test Structure

```python
def test_something():
    """Test description."""
    # Arrange
    input_value = "test"
    
    # Act
    result = function_to_test(input_value)
    
    # Assert
    assert result == expected_value
```

### Async Test Structure

```python
@pytest.mark.asyncio
async def test_async_something():
    """Test async description."""
    result = await async_function_to_test()
    assert result is not None
```

### Using Fixtures

```python
def test_with_config(minimal_config_dict):
    """Test using config fixture."""
    config = JenniferConfig._migrate_legacy(minimal_config_dict)
    assert config.name == "TestJennifer"
```

### Mocking Discord Objects

```python
async def test_command(mock_discord_message):
    """Test with mocked message."""
    mock_discord_message.content = "!help"
    # Test code here
```

## Coverage

Current coverage targets:
- Core modules: 80%+
- Utilities: 70%+
- Bot handlers: 60%+
- Overall: 70%+

Generate coverage report:
```bash
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

## CI/CD

Tests are automatically run on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`

See `.github/workflows/tests.yml` for CI configuration.
