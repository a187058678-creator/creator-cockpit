from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="admin")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    last_login_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AccountGroup(Base):
    __tablename__ = "account_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    remark: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    postforme_api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UserGroupMember(Base):
    __tablename__ = "user_group_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), nullable=False, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("account_groups.id"), nullable=False, index=True)
    member_role: Mapped[str] = mapped_column(String(50), nullable=False, default="editor")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WorkerToken(Base):
    __tablename__ = "worker_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    worker_code: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    issued_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    expired_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), nullable=False, index=True)
    session_token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    expired_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    account_handle: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    profile_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    avatar_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    auth_type: Mapped[str] = mapped_column(String(50), nullable=False, default="oauth2")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    connected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_type: Mapped[str] = mapped_column(String(50), nullable=False, default="Bearer")
    token_expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    profile_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_synced_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OAuthSession(Base):
    __tablename__ = "oauth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), nullable=False, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    state_token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    code_verifier: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    requested_scope_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    error_message: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    expired_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False, default="system")
    actor_code: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AssetRecord(Base):
    __tablename__ = "asset_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False, index=True)
    prefix: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TaskRecord(Base):
    __tablename__ = "task_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, default="upload")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_value: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    triggered_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    assigned_worker_code: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TaskExecutionRecord(Base):
    __tablename__ = "task_execution_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task_records.id"), nullable=False, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    worker_code: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    worker_token_id: Mapped[int | None] = mapped_column(ForeignKey("worker_tokens.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status_before: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    status_after: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WorkerNode(Base):
    __tablename__ = "worker_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    worker_code: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="idle")
    machine_info: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    capabilities: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    max_parallel_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scheduler_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    current_task_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    heartbeat_note: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    last_heartbeat_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    template_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    platform_scope_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    style_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkflowTemplateVersion(Base):
    __tablename__ = "workflow_template_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("workflow_templates.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version_name: Mapped[str] = mapped_column(String(128), nullable=False, default="v1")
    brief_schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    stage_schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    prompt_blocks_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    style_bible_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    shot_bible_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    default_model_config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WorkflowProject(Base):
    __tablename__ = "workflow_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    project_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(128), nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_templates.id"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="tiktok")
    subject_domain: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_templates.id"), nullable=True, index=True)
    template_version_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_template_versions.id"), nullable=True, index=True)
    task_record_id: Mapped[int | None] = mapped_column(ForeignKey("task_records.id"), nullable=True, index=True)
    run_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, default="single")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    brief_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    platform_targets_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    current_stage_code: Mapped[str] = mapped_column(String(64), nullable=False, default="brief_collect")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    triggered_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkflowRunStage(Base):
    __tablename__ = "workflow_run_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False, index=True)
    stage_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage_name: Mapped[str] = mapped_column(String(128), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    required_capability: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WorkflowAssetBundle(Base):
    __tablename__ = "workflow_asset_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False, index=True)
    bundle_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    bundle_name: Mapped[str] = mapped_column(String(256), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="short_video")
    primary_platform: Mapped[str] = mapped_column(String(32), nullable=False, default="tiktok")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkflowAsset(Base):
    __tablename__ = "workflow_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("workflow_asset_bundles.id"), nullable=False, index=True)
    run_stage_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_run_stages.id"), nullable=True, index=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    asset_role: Mapped[str] = mapped_column(String(64), nullable=False, default="primary")
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    file_asset_id: Mapped[int | None] = mapped_column(ForeignKey("asset_records.id"), nullable=True, index=True)
    r2_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WorkflowPublishLink(Base):
    __tablename__ = "workflow_publish_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("account_groups.id"), nullable=True, index=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("workflow_asset_bundles.id"), nullable=False, index=True)
    publish_draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="tiktok")
    title_text: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cover_asset_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_assets.id"), nullable=True)
    video_asset_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_assets.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    pushed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
