"""Schema validator for memory file frontmatter."""

from typing import Any

import frontmatter

from dmm.core.constants import (
    REQUIRED_FRONTMATTER_FIELDS,
    Confidence,
    Scope,
    Status,
)
from dmm.models.proposal import ValidationIssue


class SchemaValidator:
    """Validates memory file frontmatter schema."""

    VALID_SCOPES = {s.value for s in Scope}
    VALID_CONFIDENCES = {c.value for c in Confidence}
    VALID_STATUSES = {s.value for s in Status}

    def validate(self, content: str) -> list[ValidationIssue]:
        """Validate the frontmatter schema of memory content.
        
        Args:
            content: Full markdown content including frontmatter.
            
        Returns:
            List of validation issues found.
        """
        issues: list[ValidationIssue] = []

        if not content or not content.strip():
            issues.append(ValidationIssue(
                code="empty_content",
                message="Content is empty",
                severity="error",
                field="content",
            ))
            return issues

        if not content.strip().startswith("---"):
            issues.append(ValidationIssue(
                code="missing_frontmatter",
                message="Content must start with YAML frontmatter (---)",
                severity="error",
                field="content",
                suggestion="Add frontmatter block starting with ---",
            ))
            return issues

        try:
            post = frontmatter.loads(content)
        except Exception as e:
            issues.append(ValidationIssue(
                code="invalid_yaml",
                message=f"Failed to parse YAML frontmatter: {e}",
                severity="error",
                field="frontmatter",
            ))
            return issues

        metadata = post.metadata

        issues.extend(self._validate_required_fields(metadata))

        if not issues:
            issues.extend(self._validate_field_types(metadata))
            issues.extend(self._validate_field_values(metadata))

        issues.extend(self._validate_body(post.content))

        return issues

    def _validate_required_fields(
        self,
        metadata: dict[str, Any],
    ) -> list[ValidationIssue]:
        """Check for required fields.
        
        Args:
            metadata: The frontmatter metadata dict.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []
        
        missing = []
        for field_name in REQUIRED_FRONTMATTER_FIELDS:
            if field_name not in metadata:
                missing.append(field_name)

        if missing:
            issues.append(ValidationIssue(
                code="missing_required_fields",
                message=f"Missing required fields: {', '.join(missing)}",
                severity="error",
                field="frontmatter",
                suggestion=f"Add the following fields: {', '.join(missing)}",
            ))

        return issues

    def _validate_field_types(
        self,
        metadata: dict[str, Any],
    ) -> list[ValidationIssue]:
        """Validate field types.
        
        Args:
            metadata: The frontmatter metadata dict.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []

        if "id" in metadata and not isinstance(metadata["id"], str):
            issues.append(ValidationIssue(
                code="invalid_type",
                message="Field 'id' must be a string",
                severity="error",
                field="id",
            ))

        if "tags" in metadata:
            if not isinstance(metadata["tags"], list):
                issues.append(ValidationIssue(
                    code="invalid_type",
                    message="Field 'tags' must be a list",
                    severity="error",
                    field="tags",
                    suggestion="Use YAML list syntax: tags: [tag1, tag2]",
                ))
            else:
                for i, tag in enumerate(metadata["tags"]):
                    if not isinstance(tag, str):
                        issues.append(ValidationIssue(
                            code="invalid_type",
                            message=f"Tag at index {i} must be a string",
                            severity="error",
                            field="tags",
                        ))

        if "priority" in metadata:
            try:
                float(metadata["priority"])
            except (TypeError, ValueError):
                issues.append(ValidationIssue(
                    code="invalid_type",
                    message="Field 'priority' must be a number",
                    severity="error",
                    field="priority",
                ))

        if "usage_count" in metadata:
            if not isinstance(metadata["usage_count"], int):
                issues.append(ValidationIssue(
                    code="invalid_type",
                    message="Field 'usage_count' must be an integer",
                    severity="warning",
                    field="usage_count",
                ))

        if "supersedes" in metadata:
            if not isinstance(metadata["supersedes"], list):
                issues.append(ValidationIssue(
                    code="invalid_type",
                    message="Field 'supersedes' must be a list",
                    severity="error",
                    field="supersedes",
                ))

        if "related" in metadata:
            if not isinstance(metadata["related"], list):
                issues.append(ValidationIssue(
                    code="invalid_type",
                    message="Field 'related' must be a list",
                    severity="error",
                    field="related",
                ))

        return issues

    def _validate_field_values(
        self,
        metadata: dict[str, Any],
    ) -> list[ValidationIssue]:
        """Validate field values are within acceptable ranges/enums.
        
        Args:
            metadata: The frontmatter metadata dict.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []

        if "scope" in metadata:
            scope = metadata["scope"]
            if scope not in self.VALID_SCOPES:
                issues.append(ValidationIssue(
                    code="invalid_enum",
                    message=f"Invalid scope '{scope}'",
                    severity="error",
                    field="scope",
                    suggestion=f"Must be one of: {', '.join(sorted(self.VALID_SCOPES))}",
                ))

        if "confidence" in metadata:
            confidence = metadata["confidence"]
            if confidence not in self.VALID_CONFIDENCES:
                issues.append(ValidationIssue(
                    code="invalid_enum",
                    message=f"Invalid confidence '{confidence}'",
                    severity="error",
                    field="confidence",
                    suggestion=f"Must be one of: {', '.join(sorted(self.VALID_CONFIDENCES))}",
                ))

        if "status" in metadata:
            status = metadata["status"]
            if status not in self.VALID_STATUSES:
                issues.append(ValidationIssue(
                    code="invalid_enum",
                    message=f"Invalid status '{status}'",
                    severity="error",
                    field="status",
                    suggestion=f"Must be one of: {', '.join(sorted(self.VALID_STATUSES))}",
                ))

        if "priority" in metadata:
            try:
                priority = float(metadata["priority"])
                if not 0.0 <= priority <= 1.0:
                    issues.append(ValidationIssue(
                        code="out_of_range",
                        message=f"Priority {priority} is outside valid range [0.0, 1.0]",
                        severity="error",
                        field="priority",
                    ))
            except (TypeError, ValueError):
                pass

        if "id" in metadata:
            memory_id = metadata["id"]
            if isinstance(memory_id, str):
                if not memory_id.startswith("mem_"):
                    issues.append(ValidationIssue(
                        code="invalid_format",
                        message=f"Memory ID '{memory_id}' should start with 'mem_'",
                        severity="warning",
                        field="id",
                        suggestion="Use format: mem_YYYY_MM_DD_NNN",
                    ))

        if "tags" in metadata and isinstance(metadata["tags"], list):
            if len(metadata["tags"]) == 0:
                issues.append(ValidationIssue(
                    code="empty_tags",
                    message="Tags list is empty",
                    severity="warning",
                    field="tags",
                    suggestion="Add at least one relevant tag",
                ))

        scope = metadata.get("scope")
        expires = metadata.get("expires")
        if scope == "ephemeral" and expires is None:
            issues.append(ValidationIssue(
                code="missing_expires",
                message="Ephemeral memories should have an 'expires' field",
                severity="warning",
                field="expires",
                suggestion="Add an expiration date for ephemeral memories",
            ))

        confidence = metadata.get("confidence")
        status = metadata.get("status")
        if confidence == "deprecated" and status != "deprecated":
            issues.append(ValidationIssue(
                code="status_mismatch",
                message="Confidence is 'deprecated' but status is not",
                severity="warning",
                field="status",
                suggestion="Set status to 'deprecated' to match confidence",
            ))

        return issues

    def _validate_body(self, body: str) -> list[ValidationIssue]:
        """Validate the markdown body content.
        
        Args:
            body: The markdown body after frontmatter.
            
        Returns:
            List of validation issues.
        """
        issues: list[ValidationIssue] = []

        if not body or not body.strip():
            issues.append(ValidationIssue(
                code="empty_body",
                message="Memory body is empty",
                severity="error",
                field="body",
                suggestion="Add content after the frontmatter",
            ))
            return issues

        lines = body.strip().split("\n")
        has_title = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("##"):
                has_title = True
                break

        if not has_title:
            issues.append(ValidationIssue(
                code="missing_title",
                message="No H1 heading found in body",
                severity="warning",
                field="body",
                suggestion="Add a title using # Heading syntax",
            ))

        return issues

    def extract_metadata(self, content: str) -> dict[str, Any] | None:
        """Extract metadata from content without full validation.
        
        Args:
            content: Full markdown content.
            
        Returns:
            Metadata dict if parseable, None otherwise.
        """
        try:
            if not content or not content.strip().startswith("---"):
                return None
            post = frontmatter.loads(content)
            if not post.metadata:
                return None
            return dict(post.metadata)
        except Exception:
            return None
