"""
Unit tests for ConsentLogger (logging.py)
Tests: Log format, File creation, Entry structure
"""
import sys
import os
import json
from datetime import datetime, timezone

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from utils.logging import ConsentLogger


class TestConsentLogger:
    """Test ConsentLogger functionality"""

    def test_log_entry_structure(self):
        """Log entry must contain required fields"""
        logger = ConsentLogger()
        session_id = "test-session-123"
        decision = "accepted"
        
        logger.log(session_id, decision, policy_version="1.0")
        
        # Read the log file
        log_path = os.path.join('logs', 'consent', f"{session_id}.jsonl")
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                entry = json.load(f)
            
            assert entry["session_id"] == session_id
            assert entry["decision"] == decision
            assert "timestamp" in entry
            assert entry["policy_version"] == "1.0"
            
            # Cleanup
            os.remove(log_path)

    def test_timestamp_is_iso8601(self):
        """Timestamp must be ISO 8601 format with timezone"""
        logger = ConsentLogger()
        session_id = "test-session-timestamp"
        
        logger.log(session_id, "accepted")
        
        log_path = os.path.join('logs', 'consent', f"{session_id}.jsonl")
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                entry = json.load(f)
            
            # Should be parseable as ISO 8601
            timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            assert timestamp is not None
            
            os.remove(log_path)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
