# Configuration System Documentation

## Overview

The project utilizes a centralized, robust configuration system located in `src/config`. This system transitions the application from a flat-file structure to a modular, object-oriented approach. It is designed to:
- handle environment variables, 
- ensure type safety, 
- provide default values while maintaining backward compatibility with the root `config.py` file.

The system is exposed via a singleton instance `config` imported from `src.config`, ensuring consistent state throughout the application lifecycle.

The system hides logic fragments that were previously visible to the customer, guarding the application architecture from an urestricted access to the internal code parts.

## Features

- **Modular Architecture**: Settings are grouped by domain (e.g., `config.llm`, `config.cache`, `config.weaviate`), improving code readability and IDE autocomplete support.

- **Type Safety**: The system strictly enforces data types. It attempts to cast environment variables to the correct Python types (e.g., `int`, `bool`, `float`) and raises errors on startup if the conversion fails.

- **Priority Resolution**: Parameters are resolved dynamically in the following order:
    - System Environment Variables (`.env`): Highest priority.
    - `config.py`: checked if the environment variable is missing.
    - Default Values: Defined explicitly in the loader logic.

- **Validation**: Critical parameters can be marked as required. If a required setting is missing from both the environment and the config file, the application prevents startup to avoid runtime errors.

- **Constraint Checking**: Specific fields support strict allowable values (e.g., `Literal['local', 'cloud']`).

## Basic Usage

For simple parameters or quick additions that do not require strict type enforcement or grouping, you can use the dynamic `get()` method.

**Step 1: Define the Parameter**

Add your parameter to the root `config.py` file or your `.env` file.

**Option A**: `config.py`
```Python
# config.py
NEW_FEATURE_ENABLED = True
```

**Option B**: `.env`
```Bash
# .env
NEW_FEATURE_ENABLED=True
```

**Step 2: Access the Parameter**

Import the config object and use the get method.
```Python
from src.config import config

# Retrieve the parameter (returns None if not found)
is_enabled = config.get('NEW_FEATURE_ENABLED')

# Retrieve with a fallback default
retry_count = config.get('MAX_RETRIES', default=3)
```

## Creating Subconfigs (Recommended)

**Why use this approach?**

The modular approach is the standard for this project. It provides IDE autocompletion, type hinting, and early error detection. By grouping related settings into classes, we prevent the "global variable soup" problem and ensure that if a configuration is invalid (e.g., a string passed where an integer is needed), the application fails fast with a clear error message.

**Step 1: Place a new parameter in `config.py`**

Define your default values in `config.py` to serve as the baseline configuration.
Additionally, a documentation comment can be provided above the newly created parameter to explain it's usage in code.
```Python
# config.py
# ... existing configs ...

# ================= New Module Configuration =================

MY_NEW_TIMEOUT = 30

# A string, either 'standard' or 'enchanced'. Sets the operating mode of my new feature.
MY_NEW_MODE = 'standard'
```

**Step 2: Create a new subconfig class**

Open `src/config/configs.py`. Create a new class to group your settings.

Use the `_get` utility function to map the parameter name to a class attribute.

- param: The exact name of the variable in config.py or .env.

- type_: (Optional) The target Python type. The loader will attempt to cast the value. If it fails (e.g., "abc" -> int), a ValueError is raised.

- default: (Optional) A hard fallback if the value exists nowhere else.

To enforce allowable values, use Python's `Literal` type hint.

```Python
# src/config/configs.py
from typing import Literal

# ... existing imports ...

class MyNewConfig:
    # Basic integer with type enforcement
    TIMEOUT: int = _get('MY_NEW_TIMEOUT', type_=int)
    
    # String with specific allowable values (for type hinting)
    MODE: Literal['standard', 'turbo'] = _get('MY_NEW_MODE', default='standard')

    # Boolean with a default
    ENABLE_LOGS: bool = _get('ENABLE_NEW_LOGS', default=False, type_=bool)
```

**Step 3: Register the Subconfig**

Open `src/config/__init__.py`. Initialize your new class within the AppConfig wrapper. This ensures it is instantiated as part of the global singleton.
```Python
# src/config/__init__.py
from src.config.configs import *
# ...

class AppConfig:
    # ... existing subconfigs ...
    convstate:  ConversationStateConfig = ConversationStateConfig()
    processing: ProcessingConfig        = ProcessingConfig()
    
    # ==== Add your new config here ====
    mynewmodule: MyNewConfig            = MyNewConfig()
    
    # ...
```

**Usage:**

You can now access your settings with full type support:
```Python
from src.config import config

if config.mynewmodule.MODE == 'turbo':
    print(f"Timeout is: {config.mynewmodule.TIMEOUT}")
```
