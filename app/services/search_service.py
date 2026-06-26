from __future__ import annotations

import hashlib
import mimetypes
import re
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import fitz
import numpy as np
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
)
from azure.storage.blob import BlobServiceClient, ContentSettings
from pypdf import PdfReader
from rapidocr_onnxruntime import RapidOCR

from app.config import get_settings
from app.exceptions import ConfigurationError, ExternalServiceError
from app.services.azure_auth import get_azure_credential, get_blob_credential
from app.services.trace_store import record_trace

SUPPORTED_KNOWLEDGE_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv"}


def supported_knowledge_extensions() -> list[str]:
    return sorted(SUPPORTED_KNOWLEDGE_EXTENSIONS)


def _search_credential() -> object:
    settings = get_settings()
    if settings.azure_ai_search_api_key:
        return AzureKeyCredential(settings.azure_ai_search_api_key)
    return get_azure_credential()


def _search_client(index_name: str | None = None) -> SearchClient:
    settings = get_settings()
    return SearchClient(
        endpoint=settings.resolved_search_endpoint,
        index_name=index_name or settings.azure_ai_search_index,
        credential=_search_credential(),
    )


def _index_client() -> SearchIndexClient:
    settings = get_settings()
    return SearchIndexClient(endpoint=settings.resolved_search_endpoint, credential=_search_credential())


def _blob_service_client() -> tuple[BlobServiceClient, str]:
    settings = get_settings()
    if not settings.resolved_blob_service_url or not settings.azure_storage_container_name:
        raise ConfigurationError(
            "AZURE_STORAGE_BLOB_SERVICE_URL 或 AZURE_STORAGE_CONTAINER_NAME 未配置，当前无法上传原始文件到 Blob Storage。"
        )
    credential, auth_mode = get_blob_credential()
    return BlobServiceClient(
        account_url=settings.resolved_blob_service_url,
        credential=credential,
    ), auth_mode


def _normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\r", "\n").replace("\t", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


def _chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 180) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    separators = ["。", "！", "？", "；", "\n"]
    while start < len(text):
        end = min(len(text), start + max_chars)
        candidate = text[start:end]
        if end < len(text):
            split_points = [candidate.rfind(token) for token in separators]
            best_split = max(split_points)
            if best_split > int(max_chars * 0.55):
                end = start + best_split + 1
                candidate = text[start:end]

        candidate = candidate.strip()
        if candidate:
            chunks.append(candidate)

        if end >= len(text):
            break
        start = max(0, end - overlap)

    return chunks


def _extract_pdf_text_pages(file_path: Path) -> list[str]:
    reader = PdfReader(str(file_path))
    extracted_pages = [_normalize_text(page.extract_text() or "") for page in reader.pages]
    if any(extracted_pages):
        return extracted_pages

    document = fitz.open(str(file_path))
    engine = RapidOCR()
    ocr_pages: list[str] = []
    for page in document:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        ocr_result, _ = engine(image)
        text = "\n".join(item[1] for item in (ocr_result or []))
        ocr_pages.append(_normalize_text(text))
    return ocr_pages


def _read_text_file(file_path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return file_path.read_text(errors="ignore")


def _xml_text_from_zip(file_path: Path, name_pattern: str, *, include_values: bool = False) -> list[str]:
    text_values: list[str] = []
    with zipfile.ZipFile(file_path) as archive:
        for name in sorted(archive.namelist()):
            if not re.fullmatch(name_pattern, name):
                continue
            try:
                root = ElementTree.fromstring(archive.read(name))
            except ElementTree.ParseError:
                continue

            for element in root.iter():
                tag = element.tag.rsplit("}", 1)[-1]
                if tag == "t" or (include_values and tag == "v"):
                    value = (element.text or "").strip()
                    if value:
                        text_values.append(value)
    return text_values


def _extract_docx_pages(file_path: Path) -> list[str]:
    values = _xml_text_from_zip(file_path, r"word/(document|header\d*|footer\d*)\.xml")
    return [_normalize_text("\n".join(values))]


def _extract_pptx_pages(file_path: Path) -> list[str]:
    pages: list[str] = []
    with zipfile.ZipFile(file_path) as archive:
        slide_names = [name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
    for slide_name in sorted(slide_names):
        values = _xml_text_from_zip(file_path, re.escape(slide_name))
        pages.append(_normalize_text("\n".join(values)))
    return pages


def _extract_xlsx_pages(file_path: Path) -> list[str]:
    pages: list[str] = []
    shared_strings = _xml_text_from_zip(file_path, r"xl/sharedStrings\.xml")
    if shared_strings:
        pages.append(_normalize_text("\n".join(shared_strings)))

    values = _xml_text_from_zip(file_path, r"xl/worksheets/sheet\d+\.xml", include_values=True)
    if values:
        pages.append(_normalize_text("\n".join(values)))
    return pages


def _extract_text_pages(file_path: Path) -> list[str]:
    extension = file_path.suffix.lower()
    if extension == ".pdf":
        return _extract_pdf_text_pages(file_path)
    if extension in {".txt", ".md", ".csv"}:
        return [_normalize_text(_read_text_file(file_path))]
    if extension == ".docx":
        return _extract_docx_pages(file_path)
    if extension == ".pptx":
        return _extract_pptx_pages(file_path)
    if extension == ".xlsx":
        return _extract_xlsx_pages(file_path)

    supported = ", ".join(supported_knowledge_extensions())
    raise ConfigurationError(f"Unsupported knowledge file type: {extension or '(none)'}. Supported: {supported}")


def ensure_search_index() -> dict:
    settings = get_settings()
    index = SearchIndex(
        name=settings.azure_ai_search_index,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
            SearchableField(
                name="title",
                type=SearchFieldDataType.String,
                analyzer_name="zh-Hans.lucene",
                sortable=True,
                filterable=True,
            ),
            SearchableField(
                name="source_file",
                type=SearchFieldDataType.String,
                analyzer_name="zh-Hans.lucene",
                sortable=True,
                filterable=True,
                facetable=True,
            ),
            SearchableField(
                name="blob_path",
                type=SearchFieldDataType.String,
                filterable=True,
                sortable=True,
            ),
            SimpleField(name="page_number", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SimpleField(name="chunk_order", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SearchableField(
                name="section",
                type=SearchFieldDataType.String,
                analyzer_name="zh-Hans.lucene",
                filterable=True,
            ),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="zh-Hans.lucene"),
            SimpleField(
                name="updated_at",
                type=SearchFieldDataType.DATE_TIME_OFFSET,
                filterable=True,
                sortable=True,
            ),
        ],
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name=settings.azure_ai_search_semantic_config,
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                        keywords_fields=[
                            SemanticField(field_name="section"),
                            SemanticField(field_name="source_file"),
                        ],
                    ),
                )
            ]
        ),
    )

    try:
        _index_client().create_or_update_index(index)
        return {
            "ok": True,
            "index_name": settings.azure_ai_search_index,
            "semantic_config": settings.azure_ai_search_semantic_config,
            "endpoint": settings.resolved_search_endpoint,
        }
    except ConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Azure AI Search 索引创建失败: {exc}") from exc


def _blob_name_for_file(file_path: Path) -> str:
    fingerprint = _file_fingerprint(file_path)[:12]
    safe_name = re.sub(r"[\\/#?]+", "-", file_path.name).strip(" .-") or "knowledge-file"
    return f"knowledge-base/{fingerprint}-{safe_name}"


def _file_fingerprint(file_path: Path) -> str:
    return hashlib.sha1(file_path.read_bytes()).hexdigest()


def _upload_blob(file_path: Path) -> dict[str, Any]:
    settings = get_settings()
    blob_service, auth_mode = _blob_service_client()
    container = blob_service.get_container_client(settings.azure_storage_container_name)
    blob_name = _blob_name_for_file(file_path)
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    try:
        blob_client = container.get_blob_client(blob_name)
        with file_path.open("rb") as data:
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
                metadata={
                    "sourcefile": re.sub(r"[^0-9A-Za-z._-]+", "-", file_path.name)[:128] or "knowledge-file",
                    "uploadedat": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
        return {
            "uploaded": True,
            "auth_mode": auth_mode,
            "blob_name": blob_name,
            "blob_url": f"{settings.resolved_blob_service_url}/{settings.azure_storage_container_name}/{blob_name}",
            "container_name": settings.azure_storage_container_name,
        }
    except HttpResponseError as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(
            "Blob Storage 上传失败，请确认当前登录身份或托管身份已被授予 "
            "'Storage Blob Data Contributor' 或更高角色。"
        ) from exc


def _build_documents(
    file_path: Path,
    title: str | None,
    blob_path: str | None,
    *,
    source_file_name: str | None = None,
) -> list[dict[str, Any]]:
    source_title = title or file_path.stem
    source_file = source_file_name or file_path.name
    doc_prefix = _file_fingerprint(file_path)[:16]
    indexed_at = datetime.now(UTC)
    page_texts = _extract_text_pages(file_path)

    documents: list[dict[str, Any]] = []
    for page_number, page_text in enumerate(page_texts, start=1):
        if not page_text:
            continue

        for chunk_order, chunk in enumerate(_chunk_text(page_text), start=1):
            documents.append(
                {
                    "id": f"{doc_prefix}-p{page_number:04d}-c{chunk_order:04d}",
                    "title": source_title,
                    "source_file": source_file,
                    "blob_path": blob_path or file_path.as_posix(),
                    "page_number": page_number,
                    "chunk_order": chunk_order,
                    "section": f"page-{page_number}",
                    "content": chunk,
                    "updated_at": indexed_at,
                }
            )
    return documents


def _odata_escape(value: str) -> str:
    return value.replace("'", "''")


def _delete_existing_document_chunks(client: SearchClient, *, title: str, source_file: str) -> int:
    filters = [
        f"title eq '{_odata_escape(title)}'",
        f"source_file eq '{_odata_escape(source_file)}'",
    ]
    ids: dict[str, dict[str, str]] = {}
    for filter_expression in filters:
        results = client.search(
            search_text="*",
            filter=filter_expression,
            select=["id"],
            top=1000,
            include_total_count=False,
        )
        for item in results:
            document_id = item.get("id")
            if document_id:
                ids[document_id] = {"id": document_id}

    if not ids:
        return 0

    delete_results = client.delete_documents(documents=list(ids.values()))
    return sum(1 for item in delete_results if item.succeeded)


def ingest_file_to_knowledge_base(
    file_path: str,
    title: str | None = None,
    *,
    source_file_name: str | None = None,
) -> dict:
    target_file = Path(file_path)
    if not target_file.exists():
        raise ConfigurationError(f"知识库文件不存在: {target_file}")
    if target_file.suffix.lower() not in SUPPORTED_KNOWLEDGE_EXTENSIONS:
        supported = ", ".join(supported_knowledge_extensions())
        raise ConfigurationError(f"Unsupported knowledge file type: {target_file.suffix or '(none)'}. Supported: {supported}")

    ensure_search_index()
    blob_result = _upload_blob(target_file)
    source_title = title or target_file.stem
    clean_source_file = source_file_name or target_file.name
    documents = _build_documents(
        target_file,
        source_title,
        blob_result["blob_url"],
        source_file_name=clean_source_file,
    )
    if not documents:
        raise ExternalServiceError("File was read, but no indexable text content was extracted.")

    try:
        client = _search_client()
        deleted_existing = _delete_existing_document_chunks(
            client,
            title=source_title,
            source_file=clean_source_file,
        )
        result = client.upload_documents(documents)
        succeeded = sum(1 for item in result if item.succeeded)
        return {
            "ok": True,
            "source_file": clean_source_file,
            "document_count": succeeded,
            "deleted_existing_documents": deleted_existing,
            "blob_uploaded": blob_result["uploaded"],
            "blob_auth_mode": blob_result["auth_mode"],
            "blob_container": blob_result["container_name"],
            "blob_name": blob_result["blob_name"],
            "blob_path": blob_result["blob_url"],
            "index_name": get_settings().azure_ai_search_index,
        }
    except ConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Azure AI Search 文档导入失败: {exc}") from exc


def ingest_pdf_to_knowledge_base(file_path: str, title: str | None = None) -> dict:
    return ingest_file_to_knowledge_base(file_path, title)


def _caption_text(item: Any) -> str | None:
    captions = item.get("@search.captions") or []
    if not captions:
        return None

    first_caption = captions[0]
    if isinstance(first_caption, dict):
        return first_caption.get("text")
    return getattr(first_caption, "text", None)


def search_knowledge(query: str, *, top: int = 5) -> dict:
    try:
        started_at = time.perf_counter()
        settings = get_settings()
        client = _search_client()
        mode = "semantic"
        requested_top = max(1, int(top or 5))
        fetch_top = min(max(requested_top * 4, requested_top), 50)

        try:
            results = list(
                client.search(
                    search_text=query,
                    top=fetch_top,
                    include_total_count=True,
                    search_fields=["title", "section", "content"],
                    query_type="semantic",
                    semantic_configuration_name=settings.azure_ai_search_semantic_config,
                    query_caption="extractive",
                )
            )
        except HttpResponseError:
            mode = "keyword"
            results = list(
                client.search(
                    search_text=query,
                    top=fetch_top,
                    include_total_count=True,
                    search_fields=["title", "section", "content"],
                )
            )

        hits: list[dict[str, Any]] = []
        seen_keys: set[tuple[Any, ...]] = set()
        for item in results:
            content = item.get("content", "")
            preview_source = _caption_text(item) or content
            preview_key = re.sub(r"\s+", " ", str(preview_source)).strip()[:240]
            dedupe_key = (
                item.get("title"),
                item.get("page_number"),
                preview_key[:160],
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            hits.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "source_file": item.get("source_file"),
                    "page_number": item.get("page_number"),
                    "chunk_order": item.get("chunk_order"),
                    "content_preview": preview_source[:320] + ("..." if len(preview_source) > 320 else ""),
                    "score": item.get("@search.score"),
                    "reranker_score": item.get("@search.reranker_score"),
                }
            )
            if len(hits) >= requested_top:
                break

        payload = {
            "ok": True,
            "query": query,
            "mode": mode,
            "results": hits,
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
        }
        record_trace(
            channel="grounding",
            kind="kb_search",
            title="Azure AI Search evidence",
            message=f"{len(hits)} KB snippets returned for: {query}",
            payload=payload,
        )
        return payload
    except ConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - external service branch
        raise ExternalServiceError(f"Azure AI Search 检索失败: {exc}") from exc
