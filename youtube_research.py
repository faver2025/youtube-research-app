import os
import sys
import json
import argparse
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Google API imports
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Load environment variables
load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Drive API Scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_youtube_client():
    if not YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY is not set in .env file.")
        sys.exit(1)
    return build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

def suggest_keywords(keyword):
    """YouTubeサジェストAPIを使用して関連キーワードを取得します。"""
    url = f"http://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={keyword}"
    response = requests.get(url)
    if response.status_code == 200:
        suggestions = response.json()[1]
        print(json.dumps(suggestions, ensure_ascii=False))
        return suggestions
    else:
        print(json.dumps([]))
        return []

def extract_data(keywords_str, max_results=10):
    """YouTube APIを使用して動画データを抽出します。"""
    youtube = get_youtube_client()
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    
    all_video_data = []
    
    for kw in keywords:
        # Search videos
        search_response = youtube.search().list(
            q=kw,
            part='id,snippet',
            maxResults=max_results,
            type='video'
        ).execute()
        
        video_ids = []
        channel_ids = []
        video_map = {}
        
        for item in search_response.get('items', []):
            vid = item['id']['videoId']
            cid = item['snippet']['channelId']
            video_ids.append(vid)
            if cid not in channel_ids:
                channel_ids.append(cid)
            
            video_map[vid] = {
                'Keyword': kw,
                'Video ID': vid,
                'Title': item['snippet']['title'],
                'Channel ID': cid,
                'Channel Name': item['snippet']['channelTitle'],
                'URL': f"https://www.youtube.com/watch?v={vid}"
            }
        
        if not video_ids:
            continue
            
        # Get video statistics (views)
        videos_response = youtube.videos().list(
            part='statistics',
            id=','.join(video_ids)
        ).execute()
        
        for item in videos_response.get('items', []):
            vid = item['id']
            stats = item.get('statistics', {})
            video_map[vid]['Views'] = int(stats.get('viewCount', 0))
            
        # Get channel statistics (subscribers)
        channels_response = youtube.channels().list(
            part='statistics',
            id=','.join(channel_ids)
        ).execute()
        
        channel_subs_map = {}
        for item in channels_response.get('items', []):
            cid = item['id']
            stats = item.get('statistics', {})
            # Subscriber count can be hidden
            subs = stats.get('subscriberCount', 0)
            channel_subs_map[cid] = int(subs) if subs else 0
            
        # Calculate V/S Ratio and combine
        for vid, data in video_map.items():
            cid = data['Channel ID']
            subs = channel_subs_map.get(cid, 0)
            data['Subscribers'] = subs
            if subs > 0:
                vs_ratio = round(data['Views'] / subs, 2)
                data['V/S Ratio'] = vs_ratio
                if vs_ratio >= 10.0:
                    data['Priority'] = 'S'
                elif vs_ratio >= 3.0:
                    data['Priority'] = 'A'
                elif vs_ratio >= 1.0:
                    data['Priority'] = 'B'
                else:
                    data['Priority'] = 'C'
            else:
                data['V/S Ratio'] = 0.0
                data['Priority'] = 'C'
            all_video_data.append(data)
            
    if not all_video_data:
        print("No data found.")
        return None, None
        
    df = pd.DataFrame(all_video_data)
    # Reorder columns
    cols = ['Priority', 'Keyword', 'Title', 'Channel Name', 'Views', 'Subscribers', 'V/S Ratio', 'URL']
    df = df[cols]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"youtube_research_data_{timestamp}.xlsx"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with pd.ExcelWriter(filepath) as writer:
        # 全データの一覧シート
        df.sort_values(by=['Priority', 'Views'], ascending=[True, False]).to_excel(writer, sheet_name='All Data', index=False)
        
        # キーワードごとのシート
        for kw in df['Keyword'].unique():
            safe_kw = str(kw).replace('/', '_').replace('\\', '_')[:31]
            df_kw = df[df['Keyword'] == kw].sort_values(by=['Priority', 'Views'], ascending=[True, False])
            df_kw.to_excel(writer, sheet_name=safe_kw, index=False)
            
    print(f"Data extracted and saved to: {filepath}")
    return filepath, df

def get_comments(input_excel):
    """上位動画のコメントを取得します。"""
    if not os.path.exists(input_excel):
        print(f"File not found: {input_excel}")
        sys.exit(1)
        
    df = pd.read_excel(input_excel)
    
    # Sort by Views descending and get top 10 unique videos
    df_sorted = df.sort_values(by='Views', ascending=False).drop_duplicates(subset=['URL']).head(10)
    
    youtube = get_youtube_client()
    all_comments = {}
    
    for _, row in df_sorted.iterrows():
        url = row['URL']
        vid = url.split('v=')[-1]
        title = row['Title']
        
        try:
            comment_response = youtube.commentThreads().list(
                part='snippet',
                videoId=vid,
                maxResults=10,
                order='relevance'
            ).execute()
            
            comments = []
            for item in comment_response.get('items', []):
                comment_text = item['snippet']['topLevelComment']['snippet']['textDisplay']
                comments.append(comment_text)
            
            all_comments[vid] = {
                'title': title,
                'url': url,
                'comments': comments
            }
        except Exception as e:
            # Comments might be disabled
            all_comments[vid] = {
                'title': title,
                'url': url,
                'comments': [f"Could not fetch comments: {str(e)}"]
            }
            
    output_file = os.path.join(OUTPUT_DIR, "comments.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_comments, f, ensure_ascii=False, indent=2)
        
    print(f"Comments extracted and saved to: {output_file}")

def generate_markdown(input_excel):
    """Markdown形式でデータをプレビューします。"""
    if not os.path.exists(input_excel):
        print(f"File not found: {input_excel}")
        sys.exit(1)
        
    df = pd.read_excel(input_excel)
    
    print("## YouTubeリサーチ結果プレビュー\n")
    keywords = df['Keyword'].unique()
    
    for kw in keywords:
        print(f"### キーワード: {kw}")
        df_kw = df[df['Keyword'] == kw].sort_values(by='Views', ascending=False).head(10)
        
        # Markdown table header
        print("| 優先度 | タイトル | チャンネル名 | 再生数 | 登録者数 | V/S比 | URL |")
        print("|---|---|---|---|---|---|---|")
        
        for _, row in df_kw.iterrows():
            title = str(row['Title']).replace('|', '&#124;')
            channel = str(row['Channel Name']).replace('|', '&#124;')
            priority = row.get('Priority', '-')
            print(f"| {priority} | {title} | {channel} | {row['Views']:,} | {row['Subscribers']:,} | {row['V/S Ratio']} | [動画リンク]({row['URL']}) |")
        print("\n")

def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("Error: credentials.json is missing. Please place the OAuth client ID file in the root directory.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(input_excel):
    """Google Driveにファイルをアップロードし、スプレッドシートとして保存します。"""
    if not os.path.exists(input_excel):
        print(f"File not found: {input_excel}")
        sys.exit(1)
        
    drive_service = get_drive_service()
    
    file_name = os.path.basename(input_excel)
    
    file_metadata = {
        'name': file_name.replace('.xlsx', ''),
        'mimeType': 'application/vnd.google-apps.spreadsheet'
    }
    media = MediaFileUpload(input_excel, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resumable=True)
    
    print("Uploading to Google Drive...")
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    
    print(f"Upload complete!")
    print(f"Spreadsheet URL: {file.get('webViewLink')}")
    return file.get('webViewLink')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Research Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Suggest
    parser_suggest = subparsers.add_parser("suggest", help="Get related keywords")
    parser_suggest.add_argument("--keyword", required=True, help="Main keyword")
    
    # Extract
    parser_extract = subparsers.add_parser("extract", help="Extract video data")
    parser_extract.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser_extract.add_argument("--max-results", type=int, default=10, help="Max results per keyword")
    
    # Comments
    parser_comments = subparsers.add_parser("comments", help="Get comments for top videos")
    parser_comments.add_argument("--input", required=True, help="Path to input Excel file")
    
    # Markdown
    parser_markdown = subparsers.add_parser("markdown", help="Preview data in Markdown")
    parser_markdown.add_argument("--input", required=True, help="Path to input Excel file")
    
    # Upload
    parser_upload = subparsers.add_parser("upload", help="Upload to Google Drive")
    parser_upload.add_argument("--input", required=True, help="Path to input Excel file")
    
    args = parser.parse_args()
    
    if args.command == "suggest":
        suggest_keywords(args.keyword)
    elif args.command == "extract":
        extract_data(args.keywords, args.max_results)
    elif args.command == "comments":
        get_comments(args.input)
    elif args.command == "markdown":
        generate_markdown(args.input)
    elif args.command == "upload":
        upload_to_drive(args.input)
    else:
        parser.print_help()
