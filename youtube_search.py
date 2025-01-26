import logging
from typing import List, Optional
from youtubesearchpython import Playlist, ChannelsSearch, VideosSearch

logging.basicConfig(level=logging.INFO)

# youtube_search.py - Add better error recovery
def get_playlist_video_ids(playlist_link: str) -> Optional[List[str]]:
    try:
        playlist = Playlist(playlist_link)
        while True:
            try:
                if not playlist.hasMoreVideos:
                    break
                playlist.getNextVideos()
            except:
                break  # Handle API limitations
        return [video['id'] for video in playlist.videos if 'id' in video]
    except Exception as e:
        logging.error(f"Playlist failed: {str(e)}")
        return None

def get_channel_video_ids(channel_identifier: str, limit: int = 10) -> Optional[List[str]]:
    """
    Get video IDs from a YouTube channel by name/username.
    
    Args:
        channel_identifier: Channel name, username or URL
        limit: Maximum number of videos to fetch
        
    Returns:
        List of video IDs or None if failed
    """
    try:
        logging.info(f"Searching for channel: {channel_identifier}")
        
        # First find the channel ID
        channels_search = ChannelsSearch(channel_identifier, limit=1)
        channel_result = channels_search.result()
        
        if not channel_result['result']:
            logging.error("Channel not found")
            return None
            
        channel_id = channel_result['result'][0]['id']
        logging.info(f"Found channel ID: {channel_id}")
        
        # Now get channel videos
        videos_search = VideosSearch("", limit=limit, channel_id=channel_id)
        videos_result = videos_search.result()
        
        return [video['id'] for video in videos_result['result']]
    
    except Exception as e:
        logging.error(f"Failed to get channel videos: {str(e)}")
        return None
