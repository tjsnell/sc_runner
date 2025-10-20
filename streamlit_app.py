"""
Standalone Streamlit App for SC Allocation List Processing

This application uploads Excel spreadsheets containing allocation data,
maps columns, validates the data, and provides export options.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import List, Tuple, Optional
import openpyxl
from io import BytesIO

# Import domain model
from domain_model import (
    AllocationRecord, SourceSpreadsheet, ColumnMapping,
    TableSchema, MappingService, RecordTransformationService,
    SourceColumnName, AccountIdentifier
)

# Snowflake connector (optional, for database insert)
try:
    import snowflake.connector
    SNOWFLAKE_AVAILABLE = True
except ImportError:
    SNOWFLAKE_AVAILABLE = False


# ============================================================================
# APPLICATION LAYER - Orchestrates domain logic
# ============================================================================

class AllocationListProcessor:
    """Application service that orchestrates the processing"""

    def __init__(self):
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
        mappings: List[ColumnMapping],
        max_rows: int = 10
    ) -> pd.DataFrame:
        """Create a preview DataFrame showing mapped data"""
        records = []

        for row in source.data_rows[:max_rows]:
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
    ) -> Tuple[int, List[str]]:
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

    def process_all_data(
        self,
        source: SourceSpreadsheet,
        mappings: List[ColumnMapping]
    ) -> pd.DataFrame:
        """Process all data and return as DataFrame"""
        records_data = []

        for row in source.data_rows:
            try:
                record = self.transformation_service.transform_row(
                    effective_date=source.effective_date,
                    source_row=row,
                    source_spreadsheet=source,
                    mappings=mappings
                )

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

        return pd.DataFrame(records_data)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def to_csv(df: pd.DataFrame) -> bytes:
    """Convert DataFrame to CSV bytes"""
    return df.to_csv(index=False).encode('utf-8')


def to_excel(df: pd.DataFrame) -> bytes:
    """Convert DataFrame to Excel bytes"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='SC_Allocation_List')
    return output.getvalue()


@st.cache_resource
def get_snowflake_connection():
    """
    Establish Snowflake connection with SSO browser authentication.
    Connection is cached for the session.
    """
    if not SNOWFLAKE_AVAILABLE:
        raise ImportError("snowflake-connector-python is not installed")

    # Get connection parameters from secrets
    if "snowflake" not in st.secrets:
        raise ValueError("Snowflake configuration not found in secrets.toml")

    config = st.secrets["snowflake"]

    try:
        conn = snowflake.connector.connect(
            account=config["account"],
            user=config["user"],
            authenticator=config.get("authenticator", "externalbrowser"),
            role=config.get("role"),
            warehouse=config.get("warehouse"),
            database=config.get("database"),
            schema=config.get("schema")
        )
        return conn
    except Exception as e:
        st.error(f"Failed to connect to Snowflake: {e}")
        raise


def insert_to_snowflake(df: pd.DataFrame, conn, table_name: str) -> int:
    """Insert DataFrame into Snowflake table"""
    cursor = conn.cursor()

    try:
        # Prepare insert statement
        columns = df.columns.tolist()
        placeholders = ", ".join(["%s"] * len(columns))
        column_names = ", ".join(columns)

        insert_sql = f"""
            INSERT INTO {table_name} ({column_names})
            VALUES ({placeholders})
        """

        # Convert DataFrame to list of tuples
        data = [tuple(row) for row in df.values]

        # Execute batch insert
        cursor.executemany(insert_sql, data)
        conn.commit()

        return len(data)

    finally:
        cursor.close()


# ============================================================================
# PRESENTATION LAYER - Streamlit UI
# ============================================================================

def main():
    st.set_page_config(
        page_title="SC Allocation List Processor",
        page_icon="📊",
        layout="wide"
    )

    st.title("📊 SC Allocation List Processor")
    st.markdown("""
    Upload an Excel spreadsheet containing allocation data. The app will:
    1. Extract the effective date from the file
    2. Map columns to the target schema
    3. Validate the data
    4. Export processed data as CSV or Excel
    """)

    # Initialize processor
    processor = AllocationListProcessor()

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
            source = processor.parse_excel_file(file_bytes)

            # Display file info
            st.success("✅ File uploaded successfully!")

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Effective Date", str(source.effective_date))
                st.metric("Total Records", len(source.data_rows))
            with col2:
                st.info(f"**Title:** {source.title_row}")

            # Column Mapping Section
            st.header("2️⃣ Column Mapping")

            default_mappings = processor.mapping_service.get_default_mappings()

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

            # Preview Section
            st.header("3️⃣ Data Preview")

            with st.spinner("Generating preview..."):
                preview_df = processor.preview_data(source, default_mappings)
                st.dataframe(
                    preview_df,
                    use_container_width=True,
                    hide_index=True
                )

            # Validation Section
            st.header("4️⃣ Validation")

            if st.button("🔍 Validate Data", type="secondary"):
                with st.spinner("Validating records..."):
                    valid_count, errors = processor.validate_records(
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

            # Process and Export Section
            st.header("5️⃣ Process & Export Data")

            st.info("Process all records and download the results")

            col1, col2 = st.columns([1, 3])
            with col1:
                process_button = st.button(
                    "🚀 Process Data",
                    type="primary"
                )

            if process_button:
                with st.spinner("Processing data..."):
                    try:
                        processed_df = processor.process_all_data(
                            source,
                            default_mappings
                        )

                        st.success(f"""
                        ✅ Successfully processed {len(processed_df)} records

                        Effective Date: **{source.effective_date}**
                        """)

                        # Show processed data
                        st.subheader("Processed Data")
                        st.dataframe(processed_df, use_container_width=True)

                        # Download buttons
                        st.subheader("📥 Download Options")

                        col1, col2 = st.columns(2)

                        with col1:
                            csv_data = to_csv(processed_df)
                            st.download_button(
                                label="📄 Download as CSV",
                                data=csv_data,
                                file_name=f"sc_allocation_{source.effective_date}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )

                        with col2:
                            excel_data = to_excel(processed_df)
                            st.download_button(
                                label="📊 Download as Excel",
                                data=excel_data,
                                file_name=f"sc_allocation_{source.effective_date}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )

                        # Summary statistics
                        with st.expander("📊 Summary Statistics"):
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                st.metric("Total Records", len(processed_df))
                                st.metric("Total Balance", f"${processed_df['BALANCE'].sum():,.2f}")

                            with col2:
                                fraud_count = processed_df['FRAUD_WARNING'].sum()
                                st.metric("Fraud Warnings", fraud_count)
                                admin_hold_count = processed_df['ADMIN_HOLD'].sum()
                                st.metric("Admin Holds", admin_hold_count)

                            with col3:
                                unique_officers = processed_df['MANAGING_OFFICER'].nunique()
                                st.metric("Unique Officers", unique_officers)
                                unique_timeframes = processed_df['TIME_FRAME'].nunique()
                                st.metric("Unique Timeframes", unique_timeframes)

                        # Snowflake Insert Section (if available)
                        if SNOWFLAKE_AVAILABLE and "snowflake" in st.secrets:
                            st.subheader("💾 Insert to Snowflake")

                            st.warning("⚠️ This will insert data into the Snowflake table. Ensure data is validated before proceeding.")

                            col1, col2 = st.columns([1, 3])
                            with col1:
                                insert_button = st.button(
                                    "💾 Insert to Snowflake",
                                    type="secondary"
                                )

                            if insert_button:
                                with st.spinner("Connecting to Snowflake with SSO (browser will open)..."):
                                    try:
                                        # Get connection (will trigger browser SSO)
                                        conn = get_snowflake_connection()

                                        st.info("✅ Connected to Snowflake")

                                        # Get table name from config
                                        config = st.secrets["snowflake"]
                                        full_table_name = f"{config['database']}.{config['schema']}.{config.get('table', 'BI5305_SC_ALLOC_LIST')}"

                                        with st.spinner(f"Inserting {len(processed_df)} records into {full_table_name}..."):
                                            rows_inserted = insert_to_snowflake(processed_df, conn, full_table_name)

                                            st.success(f"""
                                            ✅ Successfully inserted {rows_inserted} records into Snowflake!

                                            **Table:** {full_table_name}
                                            **Effective Date:** {source.effective_date}
                                            """)

                                    except Exception as e:
                                        st.error(f"❌ Error inserting to Snowflake: {e}")
                                        st.exception(e)

                    except Exception as e:
                        st.error(f"❌ Error processing data: {e}")
                        st.exception(e)

        except Exception as e:
            st.error(f"❌ Error processing file: {e}")
            st.exception(e)

    # Sidebar with info
    with st.sidebar:
        st.header("📖 About")
        st.markdown("""
        **SC Allocation List Processor**

        This app uses domain-driven design principles:
        - **Domain Model**: Core business entities
        - **Application Layer**: Orchestration logic
        - **Presentation Layer**: Streamlit UI

        **Features:**
        - Excel file parsing
        - Automatic date extraction
        - Data validation
        - CSV/Excel export
        """)

        st.header("📋 Required Columns")
        st.markdown("""
        Your Excel file must include:
        - Row 0: Title
        - Row 1, Col A: Effective Date
        - Row 2: Headers
        - Row 3+: Data

        **Expected Headers:**
        - Account Identifier
        - Full Name
        - Balance
        - Fraud Warning - Desc
        - Admin Hold - Desc
        - Charge Off Reason Code - Desc
        - Charge Off Group - Desc
        - Managing Officer - Desc
        """)

        st.header("🔧 Configuration")
        schema = TableSchema()
        st.code(f"Table: {schema.table_name}")

        # Snowflake status
        st.header("❄️ Snowflake")
        if SNOWFLAKE_AVAILABLE:
            if "snowflake" in st.secrets:
                config = st.secrets["snowflake"]
                st.success("✅ Configured")
                st.code(f"""Account: {config.get('account', 'N/A')}
Database: {config.get('database', 'N/A')}
Schema: {config.get('schema', 'N/A')}
Table: {config.get('table', 'BI5305_SC_ALLOC_LIST')}
Auth: {config.get('authenticator', 'externalbrowser')}""")
            else:
                st.warning("⚠️ Not configured")
                st.caption("Add Snowflake credentials to `.streamlit/secrets.toml` to enable database insert")
        else:
            st.error("❌ Not installed")
            st.caption("Install: `pip install snowflake-connector-python`")


if __name__ == "__main__":
    main()