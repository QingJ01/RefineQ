"""Backup-first migration from legacy projects to personal learning workspaces."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from refineq.operations.backup import BackupResult, create_backup
from refineq.storage.json_store import AtomicJsonStore, StorageError
from refineq.storage.workspaces import WorkspaceRepository


class WorkspaceMigrationError(RuntimeError):
    """Raised before or during an unsafe legacy-data migration."""


@dataclass(frozen=True, slots=True)
class WorkspaceMigrationResult:
    migrated_count: int
    backup: BackupResult | None


@dataclass(frozen=True, slots=True)
class _LegacyProject:
    owner_id: str
    project_id: str
    path: Path
    title: str
    created_at: datetime


def _legacy_projects(data_root: Path, store: AtomicJsonStore) -> list[_LegacyProject]:
    users_root = data_root / "users"
    if not users_root.is_dir():
        return []
    projects: list[_LegacyProject] = []
    for owner_root in sorted(path for path in users_root.iterdir() if path.is_dir()):
        collection = owner_root / "projects"
        if not collection.is_dir():
            continue
        for path in sorted(collection.glob("*.json")):
            owner_id = owner_root.name
            project_id = path.stem
            try:
                data = store.read(owner_id, "projects", project_id).data
                created_at = datetime.fromisoformat(data["created_at"]).astimezone(UTC)
                title = str(data["name"]).strip()
            except (KeyError, TypeError, ValueError, StorageError) as error:
                raise WorkspaceMigrationError(f"Invalid legacy project record: {path}") from error
            if not title:
                raise WorkspaceMigrationError(f"Legacy project title is blank: {path}")
            projects.append(
                _LegacyProject(
                    owner_id=owner_id,
                    project_id=project_id,
                    path=path.resolve(),
                    title=title,
                    created_at=created_at,
                )
            )
    return projects


def _learning_context(
    store: AtomicJsonStore,
    project: _LegacyProject,
) -> tuple[str, list[str]]:
    try:
        learning = store.read(project.owner_id, "learning", project.project_id).data
    except StorageError:
        return project.title, [project.title]
    progress = learning.get("progress") or {}
    goal = str(progress.get("goal") or project.title).strip()
    raw_topics = progress.get("topics") or {}
    topic_values = raw_topics.values() if isinstance(raw_topics, dict) else raw_topics
    topics = [
        str(item.get("name") if isinstance(item, dict) else item).strip() for item in topic_values
    ]
    topics = [item for item in topics if item and item != "None"]
    return goal, list(dict.fromkeys(topics)) or [project.title]


def _preflight_conflicts(
    data_root: Path,
    store: AtomicJsonStore,
    projects: list[_LegacyProject],
) -> None:
    for project in projects:
        workspace_path = (
            data_root / "users" / project.owner_id / "workspaces" / f"{project.project_id}.json"
        )
        if not workspace_path.exists():
            continue
        try:
            existing = store.read(project.owner_id, "workspaces", project.project_id).data
        except StorageError as error:
            raise WorkspaceMigrationError(
                f"Conflicting workspace cannot be read: {workspace_path}"
            ) from error
        if existing.get("title") != project.title:
            raise WorkspaceMigrationError(
                f"Workspace conflict for {project.owner_id}/{project.project_id}"
            )


def _replace_reference(data: dict, legacy_id: str) -> dict:
    if data.get("project_id") == legacy_id:
        data["workspace_id"] = data.pop("project_id")
    return data


def _rewrite_related_records(store: AtomicJsonStore, project: _LegacyProject) -> None:
    learning_path = (
        store.data_root / "users" / project.owner_id / "learning" / f"{project.project_id}.json"
    )
    if learning_path.exists():
        store.mutate(
            project.owner_id,
            "learning",
            project.project_id,
            lambda data: _replace_reference(data, project.project_id),
        )

    sessions_root = store.data_root / "users" / project.owner_id / "sessions"
    if sessions_root.is_dir():
        for session_path in sorted(sessions_root.glob("*.json")):
            session_id = session_path.stem
            session = store.read(project.owner_id, "sessions", session_id)
            if session.data.get("project_id") == project.project_id:
                store.mutate(
                    project.owner_id,
                    "sessions",
                    session_id,
                    lambda data: _replace_reference(data, project.project_id),
                )


def migrate_projects_to_workspaces(
    data_root: Path,
    backup_archive: Path,
) -> WorkspaceMigrationResult:
    """Migrate every legacy project only after a verified full-data backup."""

    root = data_root.expanduser().resolve()
    store = AtomicJsonStore(root)
    projects = _legacy_projects(root, store)
    if not projects:
        return WorkspaceMigrationResult(migrated_count=0, backup=None)

    _preflight_conflicts(root, store, projects)
    backup = create_backup(root, backup_archive)
    workspaces = WorkspaceRepository(store)

    for project in projects:
        workspace_path = (
            root / "users" / project.owner_id / "workspaces" / f"{project.project_id}.json"
        )
        goal, topics = _learning_context(store, project)
        if not workspace_path.exists():
            workspaces.create(
                project.owner_id,
                project.project_id,
                title=project.title,
                subject="general",
                goal=goal,
                topics=topics,
                keywords=list(dict.fromkeys([project.title, *topics])),
                routing_summary="Migrated from an earlier learning record.",
                now=project.created_at,
            )
        _rewrite_related_records(store, project)
        project.path.unlink()
        with suppress(OSError):
            project.path.parent.rmdir()

    return WorkspaceMigrationResult(migrated_count=len(projects), backup=backup)
