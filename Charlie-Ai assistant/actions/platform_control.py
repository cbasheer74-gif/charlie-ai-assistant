"""
CHARLIE Phase 12: Platform Control Actions
CLI and chat actions for managing plugins, custom agents, MCP servers, and automations.
"""

from typing import Any, Dict, List, Optional
from engine.platform.core import DeveloperPlatform
from engine.platform.models import ExtensionManifest, ExtensionType, PermissionManifest


class PlatformControlActions:
    """Assistant action tools for Developer Platform."""

    def __init__(self, platform: Optional[DeveloperPlatform] = None):
        self.platform = platform or DeveloperPlatform()

    def list_installed_plugins(self) -> List[Dict[str, Any]]:
        return self.platform.plugin_registry.list_plugins()

    def install_plugin(
        self,
        plugin_id: str,
        name: str,
        version: str,
        ext_type: str,
        tools: List[str],
        allowed_domains: Optional[List[str]] = None,
        allowed_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        manifest = ExtensionManifest(
            id=plugin_id,
            name=name,
            version=version,
            type=ExtensionType(ext_type.upper()),
            description=f"Plugin {name}",
            entrypoint="main.py",
            tools=tools,
            permissions=PermissionManifest(
                network=allowed_domains or [],
                filesystem=allowed_files or [],
            ),
        )
        ok, msg = self.platform.install_plugin_from_manifest(manifest)
        return {"success": ok, "message": msg}

    def list_custom_agents(self) -> List[Dict[str, Any]]:
        agents = self.platform.agent_builder.list_agents()
        return [
            {
                "id": a.agent_id,
                "name": a.name,
                "role": a.role,
                "allowed_tools": a.allowed_tools,
                "project_scope": a.project_scope,
            }
            for a in agents
        ]

    def resolve_tools_for_goal(self, goal: str) -> List[str]:
        tools = self.platform.tool_resolver.resolve_tools_for_task(goal)
        return [t.name for t in tools]
