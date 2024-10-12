import os
import sys
import requests
from tqdm import tqdm
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# ------------------------ Configuration ------------------------

# HyperDeck Configuration
HYPERDECK_IP = '192.168.72.65'  # Replace with your HyperDeck's IP address
SD_CARD_NAME = 'Media-sd1'       # Replace with the SD card you want to access (e.g., 'Media-sd1')

# Local Download Directory
DOWNLOAD_DIR = '/ssd'  # Replace with your local directory path

# Google Drive Configuration
SERVICE_ACCOUNT_FILE = 'key/nxt-ig-a2ad1073be4b.json'  # Path to your service account key file
SCOPES = ['https://www.googleapis.com/auth/drive']
PARENT_FOLDER_ID = '0APTAHTay5f8uUk9PVA'  # Replace with the ID of the parent folder on Google Drive

# ------------------------ End of Configuration ------------------------

def get_mounted_media():
    """
    Retrieves the list of mounted media (SD cards) from the HyperDeck.
    """
    url = f'http://{HYPERDECK_IP}/mounts/'
    try:
        response = requests.get(url)
        response.raise_for_status()
        mounts = response.json()
        return mounts
    except requests.exceptions.RequestException as e:
        print(f"Error retrieving mounted media: {e}")
        return []

def find_sd_card(sd_card_name):
    """
    Finds the specified SD card in the list of mounted media.
    """
    mounts = get_mounted_media()
    for mount in mounts:
        if mount['name'] == sd_card_name:
            return mount['name']
    print(f"SD card '{sd_card_name}' not found.")
    return None

def list_files_on_sd_card(sd_card_name):
    """
    Lists all files on the specified SD card.
    """
    url = f'http://{HYPERDECK_IP}/mounts/{sd_card_name}/'
    try:
        response = requests.get(url)
        response.raise_for_status()
        files = response.json()
        return files
    except requests.exceptions.RequestException as e:
        print(f"Error listing files on {sd_card_name}: {e}")
        return []

def download_file_from_sd_card(sd_card_name, file_info):
    """
    Downloads a single file from the SD card to the local directory with a progress bar.
    """
    file_name = file_info['name']
    url = f'http://{HYPERDECK_IP}/mounts/{sd_card_name}/{file_name}'
    local_filename = os.path.join(DOWNLOAD_DIR, file_name)

    print(f"Downloading {url} to {local_filename}")

    total_size = file_info.get('size', 0)
    block_size = 8192  # 8 Kilobytes

    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            t = tqdm(total=total_size, unit='iB', unit_scale=True, desc=file_name)
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        t.update(len(chunk))
            t.close()
            actual_size = os.path.getsize(local_filename)
            if total_size != 0 and actual_size != total_size:
                print(f"WARNING: Expected size {total_size} bytes, but got {actual_size} bytes")
            print(f"Downloaded {local_filename}")
            return local_filename
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {file_name}: {e}")
        return None

def upload_file_to_drive(file_path, folder_id, drive_service):
    """
    Uploads a file to Google Drive in the specified folder.
    """
    file_name = os.path.basename(file_path)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)

    print(f"Uploading {file_name} to Google Drive folder ID {folder_id}")

    try:
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        print(f"Uploaded {file_name} with file ID: {file.get('id')}")
        return file.get('id')
    except Exception as e:
        print(f"Error uploading {file_name}: {e}")
        return None

def list_subfolders(folder_id, drive_service):
    """
    Lists all subfolders in the specified Google Drive folder.
    """
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    try:
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        folders = results.get('files', [])
        return folders
    except Exception as e:
        print(f"Error listing subfolders: {e}")
        return []

def create_drive_folder(folder_name, parent_folder_id, drive_service):
    """
    Creates a new folder in Google Drive with the specified name under the parent folder.
    """
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }

    try:
        folder = drive_service.files().create(
            body=folder_metadata,
            fields='id',
            supportsAllDrives=True
        ).execute()
        print(f"Created folder '{folder_name}' with ID: {folder.get('id')}")
        return folder.get('id')
    except Exception as e:
        print(f"Error creating folder '{folder_name}': {e}")
        return None

def authenticate_google_drive():
    """
    Authenticates with Google Drive using a service account.
    """
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    drive_service = build('drive', 'v3', credentials=credentials)
    return drive_service



def navigate_and_select_folder(parent_folder_id, drive_service):
    """
    Navigates through folders and allows the user to select or create a folder.
    """
    current_folder_id = parent_folder_id

    while True:
        # List subfolders in the current folder
        subfolders = list_subfolders(current_folder_id, drive_service)
        print("\nSelect a folder:")
        for idx, folder in enumerate(subfolders, start=1):
            print(f"[{idx}] {folder['name']}")

        # Add options for Upload Here and Create New Folder
        option_upload_here = len(subfolders) + 1
        option_create_new = len(subfolders) + 2
        print(f"[{option_upload_here}] Upload here")
        print(f"[{option_create_new}] Create new folder")

        # Get user input
        try:
            choice = int(input("Enter your choice: "))
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue

        # Handle user selection
        if 1 <= choice <= len(subfolders):
            # Move into the selected subfolder
            selected_folder = subfolders[choice - 1]
            current_folder_id = selected_folder['id']
            print(f"\nNavigated into folder '{selected_folder['name']}'")
        elif choice == option_upload_here:
            # Upload files to the current folder
            return current_folder_id
        elif choice == option_create_new:
            # Create a new folder
            folder_name = input("Enter the name of the new folder: ")
            new_folder_id = create_drive_folder(folder_name, current_folder_id, drive_service)
            if new_folder_id:
                current_folder_id = new_folder_id
                print(f"\nNavigated into new folder '{folder_name}'")
            else:
                print("Failed to create new folder.")
        else:
            print("Invalid choice. Please try again.")

def automate_process():
    """
    Automates the process of downloading files from the HyperDeck and uploading them to Google Drive.
    """
    # Ensure the download directory exists
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Authenticate with Google Drive
    drive_service = authenticate_google_drive()

    # Navigate and select the folder to upload into
    target_folder_id = navigate_and_select_folder(PARENT_FOLDER_ID, drive_service)
    if not target_folder_id:
        print("No folder selected. Exiting.")
        return

    # Find the specified SD card
    sd_card = find_sd_card(SD_CARD_NAME)
    if not sd_card:
        return

    # List files on the SD card
    files = list_files_on_sd_card(sd_card)

    # Download and upload each file
    for file_info in files:
        if file_info['type'] == 'file':
            local_file = download_file_from_sd_card(sd_card, file_info)
            if local_file:
                upload_file_to_drive(local_file, target_folder_id, drive_service)
                # Optionally, delete the local file after upload
                # os.remove(local_file)

if __name__ == '__main__':
    automate_process()
