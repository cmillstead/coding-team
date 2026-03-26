"""Shared utilities for Claude Code hooks."""

from _lib.event import parse_event, get_tool_name, get_tool_input, get_tool_result
from _lib.state import get_state_file, load_state, save_state
from _lib.git import extract_git_command, is_protected_branch, extract_file_paths
from _lib.output import block, allow, allow_with_reason, advisory
from _lib.suppression import is_recently_clean, mark_clean
