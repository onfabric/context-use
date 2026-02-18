from dataclasses import dataclass, field


@dataclass
class TaskMetadata:
    archive_id: str
    etl_task_id: str
    provider: str
    interaction_type: str
    filenames: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "archive_id": self.archive_id,
            "etl_task_id": self.etl_task_id,
            "provider": self.provider,
            "interaction_type": self.interaction_type,
            "filenames": self.filenames,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskMetadata":
        return cls(
            archive_id=data["archive_id"],
            etl_task_id=data["etl_task_id"],
            provider=data["provider"],
            interaction_type=data["interaction_type"],
            filenames=data.get("filenames", []),
        )


@dataclass
class PipelineResult:
    archive_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    threads_created: int = 0
    errors: list[str] = field(default_factory=list)
