"""Document module - 文档管理."""

from .document import (
    render_document_ui as admin_document,
    inspect_object_ui as inspect_object,
    document_module_allowed,
    extract_doc_examples,
    mask_attr_value,
    callable_smoke_eligibility,
    run_object_smoke_test,
    scan_document_modules,
    DOCUMENT_MODULE_WHITELIST,
)

from ..contexts import document_ui_ctx as document_ctx

__all__ = [
    # Main UI (aliased as admin_document for admin.py compatibility)
    'admin_document',
    # Object inspection
    'inspect_object',
    # Document utilities
    'document_module_allowed',
    'extract_doc_examples',
    'mask_attr_value',
    'callable_smoke_eligibility',
    'run_object_smoke_test',
    'scan_document_modules',
    # Context
    'document_ctx',
    # Constants
    'DOCUMENT_MODULE_WHITELIST',
]
