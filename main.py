import os
import ast
import logging
import tls_client
import time
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

REQUIRED_VARS = [
    'DISCORD_TOKEN',
    'DISCORD_USER_ID',
    'COOKIE_DCFduid',
    'COOKIE_SDCFduid',
]

missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    logger.error(f"Missing required environment variables: {', '.join(missing)}")
    logger.error("Please copy .env.example to .env and fill in the values.")
    exit(1)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_USER_ID = os.getenv('DISCORD_USER_ID')

cookies = {
    '__dcfduid': os.getenv('COOKIE_DCFduid'),
    '__sdcfduid': os.getenv('COOKIE_SDCFduid'),
    '__stripe_mid': os.getenv('COOKIE_STRIPE_MID', ''),
    'cf_clearance': os.getenv('COOKIE_CF_CLEARANCE', ''),
}

excluded_env = os.getenv('Excluded_channels', '[]')
try:
    excluded_channels = ast.literal_eval(excluded_env) if excluded_env else []
    excluded_channels = [str(ch) for ch in excluded_channels]
except (ValueError, SyntaxError) as e:
    logger.warning("No se pudo parsear Excluded_channels: %s", e)
    excluded_channels = []

logger.info(f"Excluded channels loaded: {excluded_channels}")

headers = {
    'accept': '*/*',
    'accept-language': 'en-US',
    'content-type': 'application/json',
    'authorization': DISCORD_TOKEN,
    'origin': 'https://canary.discord.com',
    'referer': 'https://canary.discord.com/channels/@me/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
}

json_data = {
    'tabs': {
        'messages': {
            'sort_by': 'timestamp',
            'sort_order': 'desc',
            'author_id': [DISCORD_USER_ID],
            'limit': 25,
        },
    },
    'track_exact_total_hits': True,
}

# Create a TLS client session
session = tls_client.Session()

# Cache de respuesta GET /channels/{id} (un ID de canal DM ≠ ID del otro usuario)
channel_data_cache = {}


def fetch_channel(channel_id):
    cid = str(channel_id)
    if cid in channel_data_cache:
        return channel_data_cache[cid]
    response = session.get(
        f'https://canary.discord.com/api/v9/channels/{cid}',
        cookies=cookies,
        headers=headers,
    )
    if response.status_code != 200:
        return None
    data = response.json()
    channel_data_cache[cid] = data
    return data


def get_channel_info(channel_id):
    cid = str(channel_id)
    data = fetch_channel(cid)
    if not data:
        return None, cid
    recipients = data.get('recipients', [])
    if recipients:
        username = recipients[0].get('username', 'unknown')
        user_id = recipients[0].get('id', cid)
    else:
        username = data.get('name', 'unknown')
        user_id = cid
    return username, user_id


def is_channel_excluded(channel_id) -> bool:
    """True si el ID del canal o algún destinatario (usuario) está en excluded_channels."""
    if not excluded_channels:
        return False
    cid = str(channel_id)
    if cid in excluded_channels:
        return True
    data = fetch_channel(cid)
    if not data:
        return False
    for r in data.get('recipients', []):
        rid = r.get('id')
        if rid is not None and str(rid) in excluded_channels:
            return True
    return False

# Function to handle rate limits and retries
def delete_message_with_retry(channel_id, message_id):
    delete_url = f'https://canary.discord.com/api/v9/channels/{channel_id}/messages/{message_id}'
    retry_attempts = 5
    while retry_attempts > 0:
        delete_response = session.delete(
            delete_url,
            cookies=cookies,
            headers=headers
        )
        
        if delete_response.status_code == 204:
            return True
        elif delete_response.status_code == 429:
            rate_limit_data = delete_response.json()
            retry_after = rate_limit_data.get("retry_after", 3)
            logger.warning(f"Rate limited. Retrying in {retry_after} seconds.")
            time.sleep(retry_after)
            time.sleep(retry_after)
            retry_attempts -= 1
        else:
            logger.error(f"Failed to delete {message_id}. Status: {delete_response.status_code} | Response: {delete_response.text}")
            return False
    
    logger.error(f"Failed to delete {message_id} after multiple attempts.")
    return False

# Function to retrieve and delete messages using cursor pagination
def retrieve_and_delete_messages():
    cursor = None
    last_channel_id = None
    total_found = 0
    total_deleted = 0
    total_failed = 0
    chats_processed = {}
    while True:
        # If we have a cursor, update the JSON data to include it
        if cursor:
            json_data['tabs']['messages']['cursor'] = cursor

        # Sending POST request to search messages
        response = session.post(
            'https://discord.com/api/v9/users/@me/messages/search/tabs',
            cookies=cookies,
            headers=headers,
            json=json_data
        )

        # Parse response
        response_data = response.json()
        messages = response_data.get('tabs', {}).get('messages', {}).get('messages', [])
        new_cursor = response_data.get('tabs', {}).get('messages', {}).get('cursor', None)

        # Process messages and ignore type 3
        processed_messages = []
        last_channel_id = None
        if messages:
            for message_list in messages:
                for message in message_list:
                    if message.get('type') == 3:  # Ignore messages with type 3
                        continue

                    channel_id = message.get('channel_id')
                    if is_channel_excluded(channel_id):
                        logger.info(
                            "Omitiendo mensaje %s: canal/usuario excluido.",
                            message.get('id'),
                        )
                        continue

                    message_id = message.get('id')
                    content = message.get('content')
                    channel_id = message.get('channel_id')

                    message_info = {
                        'Message ID': message_id,
                        'Content': content,
                        'Channel ID': channel_id,
                    }
                    processed_messages.append(message_info)

            # Delete each message with retry logic
            last_channel_id = None
            for msg in processed_messages:
                channel_id = msg['Channel ID']
                message_id = msg['Message ID']
                content = msg['Content'] or '(sin texto/imagen/adjunto)'
                total_found += 1
                
                if channel_id != last_channel_id:
                    username, user_id = get_channel_info(channel_id)
                    if username:
                        logger.info(f"\n=== Chat: {username} ({user_id}) ===")
                        if user_id not in chats_processed:
                            chats_processed[user_id] = username
                    last_channel_id = channel_id
                
                content_preview = content[:100].replace('\n', ' ') if content else '(sin texto)'
                
                logger.info(f"  [{message_id}] {content_preview}")
                
                if delete_message_with_retry(channel_id, message_id):
                    total_deleted += 1
                else:
                    total_failed += 1
                time.sleep(1.75 + 0.3)

        # If there's no cursor in the response, we're done
        if not new_cursor:
            logger.info("\n" + "="*50)
            logger.info("           RESUMEN")
            logger.info("="*50)
            logger.info(f"  Chats procesados: {len(chats_processed)}")
            logger.info(f"  Mensajes encontrados: {total_found}")
            logger.info(f"  Mensajes eliminados: {total_deleted}")
            logger.info(f"  Mensajes fallidos: {total_failed}")
            logger.info("="*50)
            break

        # Update the cursor for the next iteration
        cursor = new_cursor

# Start the process of retrieving and deleting messages
retrieve_and_delete_messages()
