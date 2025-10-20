# SC Allocation List Uploader - Complete Documentation

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Domain Model Code](#domain-model-code)
4. [Streamlit Application Code](#streamlit-application-code)
5. [Deployment Guide](#deployment-guide)
6. [Usage Instructions](#usage-instructions)
7. [Troubleshooting](#troubleshooting)

---

## Overview

This Snowflake Streamlit application uploads Excel spreadsheets containing SC Allocation List data and inserts them into the `ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST` table.

**Key Features:**
- Domain-Driven Design architecture
- Automatic effective date extraction from Excel
- Smart column mapping with transformations
- Data validation before insert
- Preview and confirmation workflow

---

## Architecture

The application follows **Domain-Driven Design** principles with three distinct layers:

### 1. Domain Layer (`domain_model.py`)
- **Entities**: Core business objects (`AllocationRecord`, `SourceSpreadsheet`)
- **Value Objects**: Immutable values (`AccountIdentifier`, `SourceColumnName`)
- **Domain Services**: Business logic (`MappingService`, `RecordTransformationService`)

### 2. Application Layer
- `AllocationListUploader`: Orchestrates the upload process
- Handles file parsing, validation, and data insertion

### 3. Presentation Layer
- Streamlit UI for user interaction
- File upload, preview, validation, and insert confirmation

---

## Domain Model Code

**File: `domain_model.py`**

```python
"""
Domain Model for SC Allocation List Upload System

This module defines the core domain entities and value objects for 
processing and mapping allocation list data from Excel to Snowflake.
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
    source (Excel) and target (Snowflake) contexts.
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
    Maps source Excel column names to target Snowflake table columns.
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
    Represents the target Snowflake table structure.
    Defines the canonical data model in the data warehouse.
    """
    database: str = "ANALYTICS"
    schema: str = "MANUAL_DATA"
    table: str = "BI5305_SC_ALLOC_LIST"
    
    @property
    def fully_qualified_name(self) -> str:
        return f"{self.database}.{self.schema}.{self.table}"
    
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
```

---

## Streamlit Application Code

**File: `streamlit_app.py`**

```python
"""
Streamlit App for SC Allocation List Upload

This application uploads Excel spreadsheets containing allocation data,
maps columns to the target Snowflake table schema, and inserts the data.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import List, Optional, Dict, Any
import snowflake.snowpark as snowpark
from snowflake.snowpark import Session
from snowflake.snowpark.functions import col
import openpyxl
from io import BytesIO

# Import domain model (assume it's in same directory or installed as package)
from domain_model import (
    AllocationRecord, SourceSpreadsheet, ColumnMapping, 
    TableSchema, MappingService, RecordTransformationService,
    SourceColumnName, AccountIdentifier
)


# ============================================================================
# APPLICATION LAYER - Orchestrates domain logic
# ============================================================================

class AllocationListUploader:
    """Application service that orchestrates the upload process"""
    
    def __init__(self, session: Session):
        self.session = session
        self.table_schema = TableSchema()
        self.mapping_service = MappingService()
        self.transformation_service = RecordTransformationService()
    
    def parse_excel_file(self, file_bytes: bytes) -> SourceSpreadsheet:
        """Parse uploaded Excel file into domain model"""
        workbook = openpyxl.load_workbook(BytesIO(file_bytes))
        sheet = workbook.active
        
        # Read all rows
        rows = list(sheet.iter_rows(values_only=True))
        
        # Extract structured data
        title_row = str(rows[0][0]) if rows[0][0] else ""
        
        # Parse effective date from row 1, column 0
        effective_date_value = rows[1][0]
        if isinstance(effective_date_value, datetime):
            effective_date = effective_date_value.date()
        elif isinstance(effective_date_value, date):
            effective_date = effective_date_value
        elif isinstance(effective_date_value, str):
            # Try parsing ISO format
            effective_date = datetime.fromisoformat(
                effective_date_value.replace('Z', '+00:00')
            ).date()
        else:
            raise ValueError(f"Cannot parse effective date: {effective_date_value}")
        
        header_row = [str(cell) if cell else "" for cell in rows[2]]
        data_rows = [list(row) for row in rows[3:] if any(row)]  # Skip empty rows
        
        return SourceSpreadsheet(
            title_row=title_row,
            effective_date=effective_date,
            header_row=header_row,
            data_rows=data_rows
        )
    
    def preview_data(
        self, 
        source: SourceSpreadsheet, 
        mappings: List[ColumnMapping]
    ) -> pd.DataFrame:
        """Create a preview DataFrame showing mapped data"""
        records = []
        
        for row in source.data_rows[:10]:  # Preview first 10 rows
            try:
                record = self.transformation_service.transform_row(
                    effective_date=source.effective_date,
                    source_row=row,
                    source_spreadsheet=source,
                    mappings=mappings
                )
                
                records.append({
                    "EFFECTIVE_DATE": record.effective_date,
                    "ACCOUNT_IDENTIFIER": record.account_identifier.value,
                    "FULL_NAME": record.full_name,
                    "BALANCE": record.balance,
                    "FRAUD_WARNING": record.fraud_warning,
                    "ADMIN_HOLD": record.admin_hold,
                    "ALLOCATION_OF_LOSS_REASON": record.allocation_of_loss_reason,
                    "TIME_FRAME": record.time_frame,
                    "MANAGING_OFFICER": record.managing_officer
                })
            except Exception as e:
                st.warning(f"Error processing row: {e}")
        
        return pd.DataFrame(records)
    
    def validate_records(
        self,
        source: SourceSpreadsheet,
        mappings: List[ColumnMapping]
    ) -> tuple[int, List[str]]:
        """Validate all records and return count and errors"""
        errors = []
        valid_count = 0
        
        for idx, row in enumerate(source.data_rows, start=4):  # Start at row 4 (data row 1)
            try:
                record = self.transformation_service.transform_row(
                    effective_date=source.effective_date,
                    source_row=row,
                    source_spreadsheet=source,
                    mappings=mappings
                )
                
                record_errors = record.validate()
                if record_errors:
                    errors.extend([f"Row {idx}: {err}" for err in record_errors])
                else:
                    valid_count += 1
                    
            except Exception as e:
                errors.append(f"Row {idx}: Failed to transform - {e}")
        
        return valid_count, errors
    
    def insert_data(
        self,
        source: SourceSpreadsheet,
        mappings: List[ColumnMapping]
    ) -> tuple[int, str]:
        """Insert data into Snowflake table"""
        records_data = []
        
        for row in source.data_rows:
            try:
                record = self.transformation_service.transform_row(
                    effective_date=source.effective_date,
                    source_row=row,
                    source_spreadsheet=source,
                    mappings=mappings
                )
                
                # Convert to dictionary for Snowpark
                records_data.append({
                    "EFFECTIVE_DATE": record.effective_date,
                    "ACCOUNT_IDENTIFIER": record.account_identifier.value,
                    "FULL_NAME": record.full_name,
                    "BALANCE": float(record.balance) if record.balance else None,
                    "FRAUD_WARNING": record.fraud_warning,
                    "ADMIN_HOLD": record.admin_hold,
                    "ALLOCATION_OF_LOSS_REASON": record.allocation_of_loss_reason,
                    "TIME_FRAME": record.time_frame,
                    "MANAGING_OFFICER": record.managing_officer
                })
            except Exception as e:
                st.error(f"Error processing row: {e}")
                continue
        
        # Create Snowpark DataFrame
        df = self.session.create_dataframe(records_data)
        
        # Insert into table
        table_name = self.table_schema.fully_qualified_name
        df.write.mode("append").save_as_table(table_name)
        
        return len(records_data), table_name


# ============================================================================
# PRESENTATION LAYER - Streamlit UI
# ============================================================================

def main():
    st.set_page_config(
        page_title="SC Allocation List Uploader",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 SC Allocation List Uploader")
    st.markdown("""
    Upload an Excel spreadsheet containing allocation data. The app will:
    1. Extract the effective date from the file
    2. Map columns to the target Snowflake table
    3. Validate the data
    4. Insert records into `ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST`
    """)
    
    # Get Snowflake session
    session = snowpark.context.get_active_session()
    uploader = AllocationListUploader(session)
    
    # File upload
    st.header("1️⃣ Upload File")
    uploaded_file = st.file_uploader(
        "Choose an Excel file",
        type=["xlsx", "xls"],
        help="Upload the SC allocation list Excel file"
    )
    
    if uploaded_file is not None:
        try:
            # Parse file
            file_bytes = uploaded_file.read()
            source = uploader.parse_excel_file(file_bytes)
            
            # Display file info
            st.success("✅ File uploaded successfully!")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Effective Date", source.effective_date)
                st.metric("Total Records", len(source.data_rows))
            with col2:
                st.info(f"**Title:** {source.title_row}")
            
            # Column Mapping Section
            st.header("2️⃣ Column Mapping")
            
            default_mappings = uploader.mapping_service.get_default_mappings()
            
            st.info("💡 Using default column mappings. Verify the mapping below:")
            
            # Display mapping table
            mapping_df = pd.DataFrame([
                {
                    "Source Column": m.source_column.value,
                    "Target Column": m.target_column,
                    "Transformation": m.transformation or "None"
                }
                for m in default_mappings
            ])
            
            st.dataframe(mapping_df, use_container_width=True, hide_index=True)
            
            # Option to customize mappings
            with st.expander("🔧 Customize Mappings (Advanced)"):
                st.warning("Custom mapping editor - Coming soon!")
                st.markdown("""
                For now, edit the `MappingService.get_default_mappings()` 
                method in the domain model to customize mappings.
                """)
            
            # Preview Section
            st.header("3️⃣ Data Preview")
            
            with st.spinner("Generating preview..."):
                preview_df = uploader.preview_data(source, default_mappings)
                st.dataframe(
                    preview_df,
                    use_container_width=True,
                    hide_index=True
                )
            
            # Validation Section
            st.header("4️⃣ Validation")
            
            if st.button("🔍 Validate Data", type="secondary"):
                with st.spinner("Validating records..."):
                    valid_count, errors = uploader.validate_records(
                        source, 
                        default_mappings
                    )
                    
                    if errors:
                        st.warning(f"⚠️ Found {len(errors)} validation errors:")
                        for error in errors[:20]:  # Show first 20 errors
                            st.error(error)
                        if len(errors) > 20:
                            st.warning(f"... and {len(errors) - 20} more errors")
                    else:
                        st.success(f"✅ All {valid_count} records are valid!")
            
            # Insert Section
            st.header("5️⃣ Insert Data")
            
            st.warning("⚠️ This will insert data into the production table. Please ensure data is validated.")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                insert_button = st.button(
                    "🚀 Insert Data",
                    type="primary",
                    disabled=False
                )
            
            if insert_button:
                with st.spinner("Inserting data into Snowflake..."):
                    try:
                        record_count, table_name = uploader.insert_data(
                            source,
                            default_mappings
                        )
                        
                        st.success(f"""
                        ✅ Successfully inserted {record_count} records into:
                        
                        **{table_name}**
                        
                        Effective Date: **{source.effective_date}**
                        """)
                        
                        # Show inserted data
                        with st.expander("📋 View Inserted Records"):
                            query = f"""
                            SELECT * FROM {table_name}
                            WHERE EFFECTIVE_DATE = '{source.effective_date}'
                            LIMIT 100
                            """
                            result_df = session.sql(query).to_pandas()
                            st.dataframe(result_df, use_container_width=True)
                        
                    except Exception as e:
                        st.error(f"❌ Error inserting data: {e}")
                        st.exception(e)
        
        except Exception as e:
            st.error(f"❌ Error processing file: {e}")
            st.exception(e)
    
    # Sidebar with info
    with st.sidebar:
        st.header("📖 About")
        st.markdown("""
        **SC Allocation List Uploader**
        
        This app uses domain-driven design principles:
        - **Domain Model**: Core business entities
        - **Application Layer**: Orchestration logic
        - **Presentation Layer**: Streamlit UI
        
        **Target Table:**
        ```
        ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST
        ```
        """)
        
        st.header("🔧 Configuration")
        schema = TableSchema()
        st.code(f"""
Database: {schema.database}
Schema: {schema.schema}
Table: {schema.table}
        """)


if __name__ == "__main__":
    main()
```

---

## Deployment Guide

### Prerequisites

- Snowflake account with Streamlit enabled
- Appropriate permissions on `ANALYTICS.MANUAL_DATA` schema
- SnowSQL or Snowflake web UI access

### Step 1: Create Target Table

```sql
CREATE OR REPLACE TABLE ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST (
    EFFECTIVE_DATE DATE,
    ACCOUNT_IDENTIFIER VARCHAR(16777216),
    FULL_NAME VARCHAR(16777216),
    BALANCE NUMBER(38,2),
    FRAUD_WARNING BOOLEAN,
    ADMIN_HOLD BOOLEAN,
    ALLOCATION_OF_LOSS_REASON VARCHAR(16777216),
    TIME_FRAME VARCHAR(16777216),
    MANAGING_OFFICER STRING
);
```

### Step 2: Create Stage for Streamlit Files

```sql
-- Create stage
CREATE STAGE IF NOT EXISTS ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE;

-- List files in stage (to verify)
LIST @ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE;
```

### Step 3: Create environment.yml

Create a file named `environment.yml` with the following content:

```yaml
name: sc_allocation_uploader
channels:
  - snowflake
  - conda-forge
dependencies:
  - python=3.11
  - snowflake-snowpark-python
  - streamlit
  - pandas
  - openpyxl
```

### Step 4: Upload Files to Stage

Using SnowSQL:

```bash
# Upload domain model
PUT file://domain_model.py @ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

# Upload Streamlit app
PUT file://streamlit_app.py @ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

# Upload environment file
PUT file://environment.yml @ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

Or using Snowflake Web UI:
1. Navigate to Data > Databases > ANALYTICS > MANUAL_DATA > Stages
2. Click on STREAMLIT_STAGE
3. Click "+ Files" button
4. Upload all three files

### Step 5: Create Streamlit App

```sql
CREATE STREAMLIT ANALYTICS.MANUAL_DATA.SC_ALLOCATION_UPLOADER
  ROOT_LOCATION = '@ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = 'YOUR_WAREHOUSE_NAME';
```

### Step 6: Grant Permissions

```sql
-- Grant permissions to the role that will use the app
GRANT USAGE ON DATABASE ANALYTICS TO ROLE YOUR_ROLE;
GRANT USAGE ON SCHEMA ANALYTICS.MANUAL_DATA TO ROLE YOUR_ROLE;
GRANT SELECT, INSERT ON TABLE ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST TO ROLE YOUR_ROLE;
GRANT READ ON STAGE ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE TO ROLE YOUR_ROLE;
GRANT USAGE ON WAREHOUSE YOUR_WAREHOUSE_NAME TO ROLE YOUR_ROLE;
```

### Step 7: Access the App

```sql
-- Get the URL for your Streamlit app
SHOW STREAMLITS IN SCHEMA ANALYTICS.MANUAL_DATA;
```

Click on the URL to open the app in your browser.

---

## Usage Instructions

### Expected Excel File Format

Your Excel file must follow this structure:

| Row | Content |
|-----|---------|
| 0 | Title (e.g., "Control Support ALREADY CODED- MidMonth") |
| 1 | Effective Date in Column A (ISO format or Excel date) |
| 2 | Column Headers |
| 3+ | Data Rows |

### Required Column Headers (Row 2)

- Account Identifier
- Full Name
- Balance
- Fraud Warning - Desc
- Admin Hold - Desc
- Charge Off Reason Code - Desc
- Charge Off Group - Desc
- Managing Officer - Desc

### Workflow

1. **Upload File**
   - Click "Choose an Excel file"
   - Select your .xlsx file
   - Wait for successful upload confirmation

2. **Verify Metadata**
   - Check the extracted Effective Date
   - Verify Total Records count
   - Review the file title

3. **Review Column Mapping**
   - Verify source columns map to correct target columns
   - Check transformation rules (e.g., YES/NO → Boolean)

4. **Preview Data**
   - Review the first 10 mapped records
   - Ensure data looks correct

5. **Validate Data**
   - Click "🔍 Validate Data"
   - Review any validation errors
   - Fix issues in source Excel file if needed

6. **Insert Data**
   - Click "🚀 Insert Data"
   - Wait for confirmation
   - Review inserted records summary

### Data Transformations

The app automatically applies these transformations:

- **YES/NO to Boolean**: "YES" → `true`, "NO" → `false`
  - Applied to: Fraud Warning, Admin Hold
- **Date Extraction**: Reads effective date from Row 1
- **String Normalization**: Trims whitespace from text fields

---

## Troubleshooting

### Error: "Cannot parse effective date"

**Cause**: Row 1, Column 0 doesn't contain a valid date

**Solution**:
- Ensure Row 1, Column 0 contains a date in ISO format (e.g., `2025-10-07`) or Excel date format
- Check for extra spaces or characters

### Error: "Column not found"

**Cause**: Excel column headers don't match expected names

**Solution**:
- Verify Row 2 contains exact column names (case-sensitive)
- Required columns:
  - Account Identifier
  - Full Name
  - Balance
  - Fraud Warning - Desc
  - Admin Hold - Desc
  - Charge Off Reason Code - Desc
  - Charge Off Group - Desc
  - Managing Officer - Desc

### Error: "Permission denied"

**Cause**: User role lacks necessary Snowflake permissions

**Solution**:
```sql
-- Run as ACCOUNTADMIN
GRANT USAGE ON DATABASE ANALYTICS TO ROLE YOUR_ROLE;
GRANT USAGE ON SCHEMA ANALYTICS.MANUAL_DATA TO ROLE YOUR_ROLE;
GRANT INSERT ON TABLE ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST TO ROLE YOUR_ROLE;
```

### Error: "Validation errors"

**Cause**: Data doesn't meet business rules

**Common Issues**:
- Empty full names
- Missing balance values
- Missing time frame

**Solution**: Review error messages and correct data in Excel file

### Error: "File upload failed"

**Cause**: File format or size issues

**Solution**:
- Ensure file is .xlsx or .xls format
- Check file isn't corrupted
- Verify file size is reasonable (<50MB)

---

## Monitoring and Maintenance

### Check Recent Uploads

```sql
SELECT 
    EFFECTIVE_DATE,
    COUNT(*) as record_count,
    SUM(BALANCE) as total_balance,
    SUM(CASE WHEN FRAUD_WARNING THEN 1 ELSE 0 END) as fraud_count,
    SUM(CASE WHEN ADMIN_HOLD THEN 1 ELSE 0 END) as admin_hold_count
FROM ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST
GROUP BY EFFECTIVE_DATE
ORDER BY EFFECTIVE_DATE DESC
LIMIT 30;
```

### Verify Data Quality

```sql
-- Check for duplicates
SELECT 
    EFFECTIVE_DATE,
    ACCOUNT_IDENTIFIER,
    COUNT(*) as duplicate_count
FROM ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST
GROUP BY EFFECTIVE_DATE, ACCOUNT_IDENTIFIER
HAVING COUNT(*) > 1;

-- Check for missing values
SELECT 
    COUNT(*) as total_records,
    SUM(CASE WHEN FULL_NAME IS NULL OR FULL_NAME = '' THEN 1 ELSE 0 END) as missing_names,
    SUM(CASE WHEN BALANCE IS NULL THEN 1 ELSE 0 END) as missing_balance,
    SUM(CASE WHEN TIME_FRAME IS NULL OR TIME_FRAME = '' THEN 1 ELSE 0 END) as missing_timeframe
FROM ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST;
```

### Update App Files

To update the application:

```bash
# Upload updated files
PUT file://domain_model.py @ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT file://streamlit_app.py @ANALYTICS.MANUAL_DATA.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

Then refresh the browser to see changes.

---

## Customization Guide

### Modify Column Mappings

Edit `domain_model.py`, find `MappingService.get_default_mappings()`:

```python
@staticmethod
def get_default_mappings() -> List[ColumnMapping]:
    return [
        # Add new mapping
        ColumnMapping(
            source_column=SourceColumnName("Your New Column"),
            target_column="TARGET_COLUMN_NAME",
            transformation="optional_transformation"
        ),
        # ... existing mappings
    ]
```

### Add Custom Transformations

In `RecordTransformationService.transform_row()`, extend the `apply_transformation` function:

```python
def apply_transformation(value, transformation: Optional[str]):
    if transformation == "yes_no_to_boolean":
        if isinstance(value, str):
            return value.upper() == "YES"
        return bool(value)
    elif transformation == "your_custom_transformation":
        # Add your custom logic here
        return custom_transform(value)
    return value
```

### Add Validation Rules

In `AllocationRecord.validate()`:

```python
def validate(self) -> List[str]:
    errors = []
    
    # Existing validations...
    
    # Add custom validation
    if self.balance < -10000:
        errors.append("Balance cannot be less than -$10,000")
    
    return errors
```

---

## File Structure

```
project/
├── domain_model.py          # Domain layer
│   ├── Value Objects
│   ├── Entities
│   ├── Domain Services
│   └── Table Schema
├── streamlit_app.py         # Application + Presentation
│   ├── AllocationListUploader
│   ├── Streamlit UI
│   └── Main workflow
└── environment.yml          # Dependencies
```

---

## Security Considerations

1. **Authentication**: Uses Snowflake's built-in authentication
2. **Authorization**: Role-based access control (RBAC)
3. **Data Validation**: All records validated before insert
4. **Audit Trail**: Consider adding audit columns:
   ```sql
   ALTER TABLE ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST
   ADD COLUMN INSERTED_BY STRING DEFAULT CURRENT_USER(),
   ADD COLUMN INSERTED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP();
   ```

---

## Resources

- [Snowflake Streamlit Documentation](https://docs.snowflake.com/en/developer-guide/streamlit/about-streamlit)
- [Snowpark Python API](https://docs.snowflake.com/en/developer-guide/snowpark/python/index)
- [Domain-Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)
- [Snowflake SQL Reference](https://docs.snowflake.com/en/sql-reference)

---

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review Snowflake logs in the app
3. Verify permissions and table structure
4. Contact your Snowflake administrator

---

**Version**: 1.0  
**Last Updated**: 2025-10-19  
**Author**: Domain-Driven Design Implementation
