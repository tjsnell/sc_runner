# Snowflake SSO Setup Guide

This guide explains how to configure the app to insert data into Snowflake using browser-based SSO authentication.

## Prerequisites

1. Snowflake account with SSO enabled
2. Your Snowflake username/email
3. Access to the target database and table

## Installation

Install the Snowflake connector:

```bash
pip install snowflake-connector-python
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

### 1. Edit `.streamlit/secrets.toml`

Update the file with your Snowflake credentials:

```toml
[snowflake]
account = "abc12345.us-east-1"  # Your Snowflake account identifier
user = "your.email@company.com"   # Your SSO username/email
authenticator = "externalbrowser"  # For SSO browser-based auth
role = "YOUR_ROLE"                 # Your Snowflake role
warehouse = "YOUR_WAREHOUSE"       # Warehouse to use
database = "ANALYTICS"
schema = "MANUAL_DATA"
table = "BI5305_SC_ALLOC_LIST"
```

### 2. Finding Your Snowflake Account Identifier

Your account identifier is in your Snowflake URL:
- URL format: `https://<account_identifier>.snowflakecomputing.com`
- Example: `https://abc12345.us-east-1.snowflakecomputing.com`
- Account identifier: `abc12345.us-east-1`

## How SSO Authentication Works

1. When you click "Insert to Snowflake", the app will initiate a browser-based SSO flow
2. Your default browser will open with your company's SSO login page
3. Log in using your SSO credentials (Okta, Azure AD, etc.)
4. Once authenticated, the browser will redirect back and the connection will be established
5. The app will then insert the data into Snowflake

## Usage

1. **Run the app:**
   ```bash
   streamlit run streamlit_app.py
   ```

2. **Upload and process your Excel file** through steps 1-5

3. **Insert to Snowflake:**
   - After processing data, scroll to "Insert to Snowflake" section
   - Click "Insert to Snowflake" button
   - Browser window will open for SSO authentication
   - Complete SSO login in the browser
   - App will insert data and show confirmation

## Troubleshooting

### Error: "snowflake-connector-python is not installed"
```bash
pip install snowflake-connector-python
```

### Error: "Snowflake configuration not found"
Check that `.streamlit/secrets.toml` exists and has the `[snowflake]` section.

### Error: "Failed to connect to Snowflake"
- Verify your account identifier is correct
- Ensure your user has access to the specified role, warehouse, database, and schema
- Check that SSO is enabled for your account

### Browser doesn't open for SSO
- Check your default browser settings
- Try manually opening the URL displayed in the terminal
- Ensure pop-ups are not blocked

### Error: "Permission denied on table"
Your Snowflake role needs INSERT permissions:
```sql
GRANT INSERT ON TABLE ANALYTICS.MANUAL_DATA.BI5305_SC_ALLOC_LIST TO ROLE YOUR_ROLE;
```

## Security Notes

- `.streamlit/secrets.toml` is automatically excluded from git (see `.gitignore`)
- Never commit this file to version control
- SSO credentials are not stored in the app
- Connection is cached during the session for performance

## Without Snowflake

The app works perfectly fine without Snowflake configuration:
- All features except "Insert to Snowflake" will work
- You can still export to CSV/Excel
- Simply don't configure `.streamlit/secrets.toml`