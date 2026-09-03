from __future__ import annotations

from dataclasses import replace

from app.config.config_loader import ConfigLoader, DatabaseConfig
from app.database.connection import DatabaseConnection
from app.project.project_registry import ProjectDefinition, ProjectRegistry


class ProjectDatabaseRoutingError(RuntimeError):
    """Raised when a project cannot be mapped to a PostgreSQL database."""


class ProjectDatabaseRouter:
    """Resolve a user-selected project to its dedicated PostgreSQL database."""

    @classmethod
    def resolve_database_config(
        cls,
        project_code: str,
    ) -> tuple[ProjectDefinition, DatabaseConfig]:
        project = ProjectRegistry.resolve(project_code)
        app_config = ConfigLoader.load()
        base = app_config.database

        database_name = base.project_databases.get(project.code)
        if not database_name:
            raise ProjectDatabaseRoutingError(
                f"No PostgreSQL database is configured for project "
                f"{project.display_name} ({project.code})."
            )

        routed = replace(
            base,
            database=database_name,
        )
        return project, routed

    @classmethod
    def create_connection(
        cls,
        project_code: str,
    ) -> tuple[ProjectDefinition, DatabaseConnection]:
        project, config = cls.resolve_database_config(project_code)
        return project, DatabaseConnection(config=config)
