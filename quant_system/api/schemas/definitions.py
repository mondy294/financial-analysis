from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DefinitionListItemOut(BaseModel):
    id: str
    display_name: str
    description: str = ""
    status: str
    published_version: str | None = None
    has_draft: bool = False
    deletable: bool = True
    updated_at: str | None = None
    created_at: str | None = None


class DefinitionDeleteOut(BaseModel):
    id: str
    deleted: bool = True
    already_gone: bool = False


class DefinitionEditableOut(BaseModel):
    id: str
    display_name: str
    description: str = ""
    status: str
    published_version: str | None = None
    source: str
    draft_updated_at: str | None = None
    updated_at: str | None = None
    body: dict[str, Any]


class DefinitionSaveIn(BaseModel):
    body: dict[str, Any]
    note: str | None = None


class DefinitionPublishIn(BaseModel):
    note: str | None = None


class DefinitionPublishOut(BaseModel):
    id: str
    published_version: str
    status: str
    body: dict[str, Any]
    note: str | None = None


class DefinitionCloneIn(BaseModel):
    new_id: str | None = Field(None, description="新策略 ID；省略则自动生成 SOURCE_COPY")
    display_name: str | None = Field(None, description="显示名；省略则加「(副本)」后缀")


class RevisionMetaOut(BaseModel):
    version: str
    note: str | None = None
    created_at: str | None = None
    created_by: str | None = None
    is_published: bool = False


class RevisionBodyOut(BaseModel):
    id: str
    version: str
    note: str | None = None
    created_at: str | None = None
    body: dict[str, Any]


class FeatureCatalogItemOut(BaseModel):
    name: str
    category: str
    kind: str
    description: str = ""
    tier: str = "universal"
    roles: list[str] | None = None
    ui_group: str = "price"
    default_target: dict[str, Any] | None = None


class EvalPreviewIn(BaseModel):
    code: str = Field(..., min_length=4)
    trade_date: str | None = None  # YYYY-MM-DD；也接受 date via coerce
    # 可选：不传则用当前 draft body；传则用请求体临时试跑（不落库）
    body: dict[str, Any] | None = None


class DryScanIn(BaseModel):
    trade_date: str | None = None
    limit: int = Field(50, ge=1, le=500)
    body: dict[str, Any] | None = None
