import os
import smartsheet
import requests
import traceback
import sys

# 1. Configuration - Pulling from GitHub Secrets
API_TOKEN = os.getenv('SMARTSHEET_API_TOKEN')
CONTROL_SHEET_ID = int(os.getenv('CONTROL_SHEET_ID'))

# Initialize Client
smartsheet_client = smartsheet.Smartsheet(API_TOKEN)
smartsheet_client.errors_as_exceptions(True)

def get_column_map(sheet):
    return {col.title: col.id for col in sheet.columns}

def is_cell_empty(cell):
    return cell.value is None and cell.formula is None and getattr(cell, 'image', None) is None

def download_attachment(sheet_id, attachment_id):
    attachment_info = smartsheet_client.Attachments.get_attachment(sheet_id, attachment_id)
    download_url = attachment_info.url
    if not download_url:
        raise Exception(f"No download URL found for attachment {attachment_id}")

    response = requests.get(download_url)
    if response.status_code != 200:
        raise Exception(f"Failed to download attachment {attachment_id} (Status {response.status_code})")
    return response.content, attachment_info.name, attachment_info.mime_type

def upload_image_to_cell(sheet_id, row_id, column_id, image_bytes, image_name, mime_type):
    url = f"https://api.smartsheet.com/2.0/sheets/{sheet_id}/rows/{row_id}/columns/{column_id}/cellimages"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": mime_type,
        "Content-Disposition": f'attachment; filename="{image_name}"'
    }
    params = {"altText": image_name}

    response = requests.post(url, headers=headers, params=params, data=image_bytes)
    if response.status_code != 200:
        raise Exception(f"Upload failed: {response.status_code} {response.text}")

def run_sync_for_sheet(target_sheet_id, target_columns):
    """Your original logic, wrapped for the Master Loop"""
    sheet = smartsheet_client.Sheets.get_sheet(target_sheet_id, include=['attachments'])
    column_map = get_column_map(sheet)

    for row in sheet.rows:
        try:
            attachments_response = smartsheet_client.Attachments.list_row_attachments(target_sheet_id, row.id)
            attachments = attachments_response.data
        except Exception as e:
            print(f"  Failed to list attachments for row {row.id}: {e}")
            continue

        if not attachments:
            continue

        row_cells = {cell.column_id: cell for cell in row.cells}

        for i in range(min(len(attachments), len(target_columns))):
            col_name = target_columns[i]
            if not col_name: continue
            
            col_id = column_map.get(col_name)
            if not col_id:
                continue

            cell = row_cells.get(col_id)
            if cell and not is_cell_empty(cell):
                continue

            attachment = attachments[i]
            try:
                file_bytes, file_name, mime_type = download_attachment(target_sheet_id, attachment.id)
                upload_image_to_cell(target_sheet_id, row.id, col_id, file_bytes, file_name, mime_type)
                print(f"  Uploaded '{file_name}' to {col_name}")
            except Exception as e:
                print(f"  Error with attachment {attachment.id}: {e}")

def main():
    print("=== FETCHING CONTROL PANEL ===")
    control_sheet = smartsheet_client.Sheets.get_sheet(CONTROL_SHEET_ID)
    
    # Map Control Sheet columns to their IDs for easy lookup
    control_col_map = {col.id: col.title for col in control_sheet.columns}

    for row in control_sheet.rows:
        # Convert row to a dict for easy access: row_data['Job Name']
        row_data = {control_col_map.get(c.column_id): c.value for c in row.cells}
        
        # Check if job is active
        active_status = str(row_data.get('Active')).upper()
        if active_status != 'TRUE':
            continue

        job_name = row_data.get('Job Name', 'Unnamed Job')
        target_sheet_id = int(row_data.get('Sheet ID'))
        
        # Build list of Target 1 through Target 10
        target_columns = [row_data.get(f'Target {i}') for i in range(1, 11) if row_data.get(f'Target {i}')]

        print(f"\nProcessing Job: {job_name} (Sheet: {target_sheet_id})")
        try:
            run_sync_for_sheet(target_sheet_id, target_columns)
        except Exception as e:
            print(f"Fatal error in job {job_name}: {e}")

if __name__ == "__main__":
    main()
