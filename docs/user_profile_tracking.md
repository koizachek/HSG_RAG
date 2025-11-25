# User Profile Tracking System

## Overview
This document describes the user profile tracking system implemented in the Executive Agent Chain.

## Features

### Tracked Profile Information

The system tracks the following user profile data:

1. **User-ID**: Unique UUID generated for each user session
2. **Name**: User's name extracted from conversation (e.g., "John Doe")
3. **Experience Years**: Years of professional experience (extracted from conversation)
4. **Leadership Years**: Years of leadership/management experience (extracted from conversation)
5. **Field**: Professional field/industry (e.g., Finance, Technology, Healthcare)
6. **Interest**: Content interests (e.g., Strategy, Innovation, Digital Transformation)
7. **Suggested Program**: Recommended program based on user profile (EMBA, IEMBA, or EMBA X)
8. **Handover**: Whether user requested appointment/contact (true/false/null)

### Additional Tracked Data
- User language (locked after first message)
- Program interests mentioned in conversation
- Topics discussed

## Configuration

Profile tracking is controlled by the `TRACK_USER_PROFILE` flag in `config.py`:

```python
TRACK_USER_PROFILE = True  # Enable/disable user profile tracking
```

## How It Works

### 1. Profile Extraction

The system uses regex patterns to extract information from user conversations:

- **Experience years**: Patterns like "10 years experience", "working for 5 years"
- **Leadership years**: Patterns like "5 years of leadership", "managed for 3 years"
- **Field**: Matches against common industries (finance, technology, healthcare, etc.)
- **Interest**: Identifies keywords like strategy, innovation, leadership, digital transformation

### 2. Program Recommendation

The system automatically suggests programs based on extracted profile:

- **EMBA**: Recommended for users with 5+ years experience and 2+ years leadership
- **IEMBA**: Recommended for users with 5+ years experience
- **emba X**: Recommended for users interested in digital/innovation/technology

### 3. Profile Logging

User profiles are logged to JSON files in `logs/user_profiles/` directory:

- Logs are created every 5 user messages
- Logs are created when a program is suggested
- File format: `profile_{user_id}_{timestamp}.json`

### Example Log File

```json
{
  "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "John Doe",
  "timestamp": "2025-11-25T10:15:30.123456",
  "experience_years": 10,
  "leadership_years": 5,
  "field": "Technology",
  "interest": "innovation, digital transformation",
  "suggested_program": "EMBA",
  "handover": true,
  "user_language": "en",
  "program_interest": ["EMBA", "EMBA X"]
}
```

## Implementation Details

### Key Methods

1. `_extract_experience_years(conversation)`: Extracts professional experience years
2. `_extract_leadership_years(conversation)`: Extracts leadership experience years
3. `_extract_field(conversation)`: Identifies professional field/industry
4. `_extract_interest(conversation)`: Identifies content interests
5. `_determine_suggested_program()`: Recommends program based on profile
6. `_update_conversation_state(query, response)`: Updates profile from conversation
7. `_log_user_profile()`: Saves profile to JSON file

### Integration

Profile tracking is integrated into the main `query()` method:

```python
if TRACK_USER_PROFILE:
    self._update_conversation_state(processed_query, formatted_response)
    # Log profile every 5 messages or when program is suggested
    message_count = len([m for m in self._conversation_history if isinstance(m, HumanMessage)])
    if (message_count % 5 == 0 or self._conversation_state.get('suggested_program')):
        self._log_user_profile()
```

## Privacy Considerations

- User profiles are stored locally in the logs directory
- Each session gets a unique UUID
- No personally identifiable information is required
- The system only extracts professional information volunteered during conversation

## Language Support

The extraction patterns support both English and German:

- English: "10 years experience", "5 years leadership"
- German: "10 Jahre Erfahrung", "5 Jahre Führung"

## Disabling Profile Tracking

To disable profile tracking, set `TRACK_USER_PROFILE = False` in `config.py`. This will:

- Skip all profile extraction
- Prevent profile logging
- Reduce processing overhead
