# SC Allocation List Processor - Standalone Streamlit App

A domain-driven design application for processing SC Allocation List Excel files with validation and export capabilities.

## 🚀 Quick Start

### Installation

1. Install Python 3.8 or higher

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running the App

```bash
streamlit run streamlit_app.py
```

The app will open in your default web browser at `http://localhost:8501`

## 📋 Features

- **Excel File Upload**: Parse Excel files with specific format
- **Automatic Date Extraction**: Reads effective date from file
- **Smart Column Mapping**: Maps source columns to target schema
- **Data Validation**: Validates business rules before processing
- **Multiple Export Formats**: Download as CSV or Excel
- **Summary Statistics**: View aggregate metrics

## 📊 Expected Excel File Format

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

## 🎯 Usage Workflow

### 1. Upload File
- Click "Choose an Excel file"
- Select your .xlsx file
- Wait for successful upload confirmation

### 2. Verify Metadata
- Check the extracted Effective Date
- Verify Total Records count
- Review the file title

### 3. Review Column Mapping
- Verify source columns map to correct target columns
- Check transformation rules (e.g., YES/NO → Boolean)

### 4. Preview Data
- Review the first 10 mapped records
- Ensure data looks correct

### 5. Validate Data
- Click "🔍 Validate Data"
- Review any validation errors
- Fix issues in source Excel file if needed

### 6. Process & Export
- Click "🚀 Process Data"
- View processed data in the app
- Download as CSV or Excel
- Review summary statistics

## 🏗️ Architecture

The application follows **Domain-Driven Design** principles with three distinct layers:

### 1. Domain Layer (`domain_model.py`)
- **Entities**: Core business objects (`AllocationRecord`, `SourceSpreadsheet`)
- **Value Objects**: Immutable values (`AccountIdentifier`, `SourceColumnName`)
- **Domain Services**: Business logic (`MappingService`, `RecordTransformationService`)

### 2. Application Layer
- `AllocationListProcessor`: Orchestrates the processing workflow
- Handles file parsing, validation, and data transformation

### 3. Presentation Layer (`streamlit_app.py`)
- Streamlit UI for user interaction
- File upload, preview, validation, and export features

## 🔄 Data Transformations

The app automatically applies these transformations:

- **YES/NO to Boolean**: "YES" → `true`, "NO" → `false`
  - Applied to: Fraud Warning, Admin Hold
- **Date Extraction**: Reads effective date from Row 1, Column A
- **String Normalization**: Trims whitespace from text fields

## 🛠️ Project Structure

```
sc_runner/
├── domain_model.py          # Domain layer (entities, value objects, services)
├── streamlit_app.py         # Application + Presentation layers
├── requirements.txt         # Python dependencies
├── README.md               # Original Snowflake specs
└── USAGE.md                # This file - standalone app usage
```

## ❗ Troubleshooting

### Error: "Cannot parse effective date"

**Cause**: Row 1, Column A doesn't contain a valid date

**Solution**:
- Ensure Row 1, Column A contains a date in ISO format (e.g., `2025-10-07`) or Excel date format
- Check for extra spaces or characters

### Error: "Column not found"

**Cause**: Excel column headers don't match expected names

**Solution**:
- Verify Row 2 contains exact column names (case-sensitive)
- See "Required Column Headers" section above

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

## 🔧 Customization

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

## 📦 Dependencies

- **streamlit**: Web application framework
- **pandas**: Data manipulation and analysis
- **openpyxl**: Excel file reading/writing

## 🔐 Data Privacy

- All processing happens locally in your browser
- No data is sent to external servers
- Files are processed in memory and not stored

## 📝 License

This is a standalone version converted from the original Snowflake Streamlit app specification.

---

**Version**: 1.0 Standalone
**Last Updated**: 2025-10-19
**Architecture**: Domain-Driven Design