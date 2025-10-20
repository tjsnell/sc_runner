"""
Domain Model for SC Allocation List Upload System

This module defines the core domain entities and value objects for
processing and mapping allocation list data from Excel.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, List
from enum import Enum


# ============================================================================
# VALUE OBJECTS
# ============================================================================

class YesNoIndicator(Enum):
    """Represents YES/NO string values from source data"""
    YES = "YES"
    NO = "NO"

    def to_boolean(self) -> bool:
        """Convert YES/NO to boolean"""
        return self == YesNoIndicator.YES


@dataclass(frozen=True)
class SourceColumnName:
    """Value object representing a column name from source Excel"""
    value: str

    def __post_init__(self):
        if not self.value or not isinstance(self.value, str):
            raise ValueError("Column name must be a non-empty string")


@dataclass(frozen=True)
class AccountIdentifier:
    """Value object for account identifier with validation"""
    value: str

    def __post_init__(self):
        if not self.value or not isinstance(self.value, str):
            raise ValueError("Account identifier must be a non-empty string")


# ============================================================================
# ENTITIES
# ============================================================================

@dataclass
class AllocationRecord:
    """
    Core domain entity representing a single allocation record.
    This is the ubiquitous language concept that exists in both
    source (Excel) and target contexts.
    """
    effective_date: date
    account_identifier: AccountIdentifier
    full_name: str
    balance: float
    fraud_warning: bool
    admin_hold: bool
    allocation_of_loss_reason: str
    time_frame: str
    managing_officer: str

    def validate(self) -> List[str]:
        """Validate business rules for an allocation record"""
        errors = []

        if not self.full_name or not self.full_name.strip():
            errors.append("Full name cannot be empty")

        if self.balance is None:
            errors.append("Balance must be provided")

        if not self.time_frame or not self.time_frame.strip():
            errors.append("Time frame must be specified")

        return errors


@dataclass
class SourceSpreadsheet:
    """
    Represents the uploaded Excel file with its specific structure.
    Encapsulates knowledge about the source file format.
    """
    title_row: str  # Row 0
    effective_date: date  # Row 1, Column 0
    header_row: List[str]  # Row 2
    data_rows: List[List]  # Row 3+

    def get_column_index(self, column_name: str) -> Optional[int]:
        """Find the index of a column by name"""
        try:
            return self.header_row.index(column_name)
        except ValueError:
            return None


@dataclass
class ColumnMapping:
    """
    Maps source Excel column names to target table columns.
    This is the translation layer between bounded contexts.
    """
    source_column: SourceColumnName
    target_column: str
    transformation: Optional[str] = None  # e.g., "yes_no_to_boolean"

    def __post_init__(self):
        valid_targets = {
            "EFFECTIVE_DATE", "ACCOUNT_IDENTIFIER", "FULL_NAME",
            "BALANCE", "FRAUD_WARNING", "ADMIN_HOLD",
            "ALLOCATION_OF_LOSS_REASON", "TIME_FRAME", "MANAGING_OFFICER"
        }
        if self.target_column not in valid_targets:
            raise ValueError(f"Invalid target column: {self.target_column}")


@dataclass
class TableSchema:
    """
    Represents the target table structure.
    Defines the canonical data model.
    """
    table_name: str = "SC_ALLOC_LIST"

    @property
    def columns(self) -> List[str]:
        return [
            "EFFECTIVE_DATE",
            "ACCOUNT_IDENTIFIER",
            "FULL_NAME",
            "BALANCE",
            "FRAUD_WARNING",
            "ADMIN_HOLD",
            "ALLOCATION_OF_LOSS_REASON",
            "TIME_FRAME",
            "MANAGING_OFFICER"
        ]


# ============================================================================
# DOMAIN SERVICES
# ============================================================================

class MappingService:
    """
    Domain service for creating standard column mappings.
    Encapsulates the mapping logic between source and target.
    """

    @staticmethod
    def get_default_mappings() -> List[ColumnMapping]:
        """Returns the standard mapping configuration"""
        return [
            ColumnMapping(
                source_column=SourceColumnName("Account Identifier"),
                target_column="ACCOUNT_IDENTIFIER"
            ),
            ColumnMapping(
                source_column=SourceColumnName("Full Name"),
                target_column="FULL_NAME"
            ),
            ColumnMapping(
                source_column=SourceColumnName("Balance"),
                target_column="BALANCE"
            ),
            ColumnMapping(
                source_column=SourceColumnName("Fraud Warning - Desc"),
                target_column="FRAUD_WARNING",
                transformation="yes_no_to_boolean"
            ),
            ColumnMapping(
                source_column=SourceColumnName("Admin Hold - Desc"),
                target_column="ADMIN_HOLD",
                transformation="yes_no_to_boolean"
            ),
            ColumnMapping(
                source_column=SourceColumnName("Charge Off Reason Code - Desc"),
                target_column="ALLOCATION_OF_LOSS_REASON"
            ),
            ColumnMapping(
                source_column=SourceColumnName("Charge Off Group - Desc"),
                target_column="TIME_FRAME"
            ),
            ColumnMapping(
                source_column=SourceColumnName("Managing Officer - Desc"),
                target_column="MANAGING_OFFICER"
            ),
        ]


class RecordTransformationService:
    """
    Domain service for transforming source data into AllocationRecords.
    Implements the anti-corruption layer between source and domain model.
    """

    @staticmethod
    def transform_row(
        effective_date: date,
        source_row: List,
        source_spreadsheet: SourceSpreadsheet,
        mappings: List[ColumnMapping]
    ) -> AllocationRecord:
        """Transform a source row into an AllocationRecord"""

        # Helper function to get value from source row
        def get_value(source_col_name: str):
            idx = source_spreadsheet.get_column_index(source_col_name)
            if idx is None or idx >= len(source_row):
                return None
            return source_row[idx]

        # Helper function to apply transformation
        def apply_transformation(value, transformation: Optional[str]):
            if transformation == "yes_no_to_boolean":
                if isinstance(value, str):
                    return value.upper() == "YES"
                return bool(value)
            return value

        # Build the record using mappings
        record_data = {"effective_date": effective_date}

        for mapping in mappings:
            value = get_value(mapping.source_column.value)
            transformed_value = apply_transformation(value, mapping.transformation)

            # Map to domain model field name (lowercase with underscores)
            field_name = mapping.target_column.lower()

            if field_name == "account_identifier":
                record_data[field_name] = AccountIdentifier(str(transformed_value))
            else:
                record_data[field_name] = transformed_value

        return AllocationRecord(**record_data)