from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .filesystem import delete_path, list_files, make_directory, read_file, replace_text, search_text, write_file
from .shell import run_command


def _string_param(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


@dataclass(slots=True)
class ToolRegistry:
    workspace_root: Path

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file from the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": _string_param("Relative path inside the workspace."),
                            "start_line": {"type": "integer", "minimum": 1},
                            "end_line": {"type": "integer", "minimum": 1},
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write a file inside the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": _string_param("Relative path inside the workspace."),
                            "content": _string_param("Full file content."),
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "make_directory",
                    "description": "Create a directory inside the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": _string_param("Relative path inside the workspace."),
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_path",
                    "description": "Delete a file or directory inside the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": _string_param("Relative path inside the workspace."),
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "replace_text",
                    "description": "Replace a text fragment in a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": _string_param("Relative path inside the workspace."),
                            "old": _string_param("Exact text to replace."),
                            "new": _string_param("Replacement text."),
                            "count": {"type": "integer", "minimum": 1, "default": 1},
                        },
                        "required": ["path", "old", "new"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files in the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": _string_param("Relative path inside the workspace."),
                            "pattern": _string_param("Optional glob filter."),
                            "max_depth": {"type": "integer", "minimum": 0, "default": 3},
                        },
                        "required": [],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_text",
                    "description": "Search for text across files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": _string_param("Relative path inside the workspace."),
                            "pattern": _string_param("Text to search for."),
                            "ignore_case": {"type": "boolean", "default": False},
                            "max_results": {"type": "integer", "minimum": 1, "default": 50},
                        },
                        "required": ["path", "pattern"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Run a shell command in the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": _string_param("Shell command to run."),
                            "timeout": {"type": "integer", "minimum": 1, "default": 120},
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def execute(self, name: str, args: dict[str, Any]) -> str:
        if name == "read_file":
            return read_file(self.workspace_root, **args)
        if name == "write_file":
            return write_file(self.workspace_root, **args)
        if name == "make_directory":
            return make_directory(self.workspace_root, **args)
        if name == "delete_path":
            return delete_path(self.workspace_root, **args)
        if name == "replace_text":
            return replace_text(self.workspace_root, **args)
        if name == "list_files":
            return list_files(self.workspace_root, **args)
        if name == "search_text":
            return search_text(self.workspace_root, **args)
        if name == "run_command":
            return run_command(self.workspace_root, **args)
        raise KeyError(name)
