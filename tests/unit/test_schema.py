"""Unit tests for detent.schema — AgentAction and related models."""

from __future__ import annotations

import pytest

from detent.schema import ActionType, AgentAction, RiskLevel


class TestAgentAction:
    """Tests for AgentAction model."""

    def test_create_file_write_action(self, sample_action: AgentAction) -> None:
        """Test creating a basic file_write AgentAction."""
        assert sample_action.action_type == ActionType.FILE_WRITE
        assert sample_action.agent == "claude-code"
        assert sample_action.tool_name == "Write"
        assert sample_action.risk_level == RiskLevel.MEDIUM

    def test_file_path_property(self, sample_action: AgentAction) -> None:
        """Test file_path extraction from tool_input."""
        assert sample_action.file_path == "/src/main.py"

    def test_content_property(self, sample_action: AgentAction) -> None:
        """Test content extraction from tool_input."""
        assert sample_action.content is not None
        assert "hello" in sample_action.content

    def test_is_file_write(self, sample_action: AgentAction) -> None:
        """Test is_file_write property."""
        assert sample_action.is_file_write is True

    def test_missing_file_path(self) -> None:
        """Test file_path is None when not in tool_input."""
        action = AgentAction(
            action_type=ActionType.SHELL_EXEC,
            agent="claude-code",
            tool_name="Bash",
            tool_input={"command": "ls -la"},
            tool_call_id="toolu_test",
            session_id="sess_test",
            checkpoint_ref="chk_test",
        )
        assert action.file_path is None
        assert action.is_file_write is False

    def test_default_risk_level(self) -> None:
        """Test default risk level is MEDIUM."""
        action = AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={"file_path": "/test.py", "content": ""},
            tool_call_id="toolu_test",
            session_id="sess_test",
            checkpoint_ref="chk_test",
        )
        assert action.risk_level == RiskLevel.MEDIUM

    def test_serialization_roundtrip(self, sample_action: AgentAction) -> None:
        """Test JSON serialization and deserialization."""
        json_data = sample_action.model_dump()
        restored = AgentAction.model_validate(json_data)
        assert restored == sample_action

    def test_json_serialization(self, sample_action: AgentAction) -> None:
        """Test model_dump_json produces valid JSON."""
        json_str = sample_action.model_dump_json()
        assert '"action_type":"file_write"' in json_str
        assert '"agent":"claude-code"' in json_str


class TestEnums:
    """Tests for ActionType and RiskLevel enums."""

    def test_action_type_values(self) -> None:
        """Test all ActionType enum values."""
        assert ActionType.FILE_WRITE.value == "file_write"
        assert ActionType.SHELL_EXEC.value == "shell_exec"
        assert ActionType.FILE_READ.value == "file_read"
        assert ActionType.WEB_FETCH.value == "web_fetch"
        assert ActionType.MCP_TOOL.value == "mcp_tool"

    def test_risk_level_values(self) -> None:
        """Test all RiskLevel enum values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"

    def test_action_type_from_string(self) -> None:
        """Test creating ActionType from string value."""
        assert ActionType("file_write") == ActionType.FILE_WRITE

    def test_invalid_action_type(self) -> None:
        """Test invalid ActionType raises ValueError."""
        with pytest.raises(ValueError):
            ActionType("invalid_type")
