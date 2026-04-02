"""
```python
"""
FILE PURPOSE
This file serves as a thin compatibility wrapper that re-exports the main settings object from app.config.
It exists to maintain backward compatibility with older FastAPI patterns where configuration was accessed 
through app/core/config.py rather than directly from app.config. This file was present since the original 
v1.x architecture and sits in the core configuration layer, providing a centralized access point for 
application settings throughout the ZetaOps Copilot backend.

WHAT THIS FILE DOES — step by step
1. Imports the main settings object from app.config module using a re-export pattern
2. Defines a getter function get_settings() that returns the imported settings object
3. Acts as a bridge between the current app.config location and legacy import patterns

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : get_settings
Type         : function
Purpose      : Returns the application's main settings object. This function provides a consistent 
               interface for accessing configuration settings across the application, regardless of 
               where the actual settings object is defined. It acts as a factory function that other 
               parts of the application can call to get the current configuration.
Parameters   : None
Returns      : The settings object from app.config containing all application configuration including 
               database URLs, JWT secrets, feature flags, and environment-specific settings
Calls        : No other functions - simply returns the imported settings object
DB/API       : No direct database queries or API calls
Side effects : None - this is a pure getter function with no mutations or external effects

WHO CALLS THIS FILE
- backend/app/main.py (likely imports settings for FastAPI app initialization)
- Various router files in backend/app/routers/ that need access to configuration
- Service files in backend/app/services/ that require environment-specific settings
- Database connection setup code that needs database URL and connection parameters
- Authentication middleware that needs JWT secret keys and token configuration

IMPORTS EXPLAINED
- `from app.config import settings`: Imports the main application settings object from the app.config 
  module, which contains all environment variables, database configurations, API keys, and feature flags 
  needed throughout the application.

INTERN NOTES
- Easiest thing to break without realising: Changing the import path in app.config without updating this 
  re-export, which would break all legacy code that imports from app.core.config
- Non-obvious design decision and why: This wrapper exists for backward compatibility - newer code should 
  import directly from app.config, but this maintains compatibility with FastAPI's traditional config structure
- Most common mistake when editing: Adding logic to get_settings() instead of keeping it as a simple getter, 
  which could introduce side effects or performance issues since settings are accessed frequently
- Which design principle this implements: Principle #3 (No .env in git. All secrets from settings.*) by 
  providing centralized access to environment-based configuration
- What to check if this file behaves unexpectedly: Verify that app.config exists and exports a settings 
  object, check for circular imports between config modules, and ensure environment variables are loaded
- v4-dev context: This is a stable pattern that should not change - any modifications to configuration 
  access patterns should maintain this compatibility layer to avoid breaking existing imports
"""
```
"""

from app.config import settings  # noqa: F401

def get_settings():
    return settings
