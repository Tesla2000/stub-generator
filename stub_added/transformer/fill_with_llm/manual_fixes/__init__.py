from stub_added.transformer.fill_with_llm.manual_fixes._base import ManualFix
from stub_added.transformer.fill_with_llm.manual_fixes.lsp_violation_fixer import (
    LspViolationFixer,
)

AnyManualFix = LspViolationFixer

__all__ = ["AnyManualFix", "ManualFix", "LspViolationFixer"]
