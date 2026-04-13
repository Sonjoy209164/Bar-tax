from enum import StrEnum


class LegalNodeType(StrEnum):
    ACT = "act"
    PART = "part"
    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    CLAUSE = "clause"
    PROVISO = "proviso"
    EXPLANATION = "explanation"
    TABLE = "table"
    ILLUSTRATION = "illustration"
    DEFINITION = "definition"


class CitationRelation(StrEnum):
    DIRECT = "direct"
    PARENT_CONTEXT = "parent_context"
    SIBLING_CONTEXT = "sibling_context"
    GOVERNING_RULE = "governing_rule"
    ATTACHED_TABLE = "attached_table"
