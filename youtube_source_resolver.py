import logging
from typing import List, Optional
from youtubesearchpython import Playlist, Channel, ChannelsSearch, VideosSearch

logging.basicConfig(level=logging.INFO)

def get_playlist_video_ids(playlist_link: str) -> Optional[List[str]]:
    """Get all video IDs from a YouTube playlist."""
    try:
        logging.info(f"Fetching videos from playlist: {playlist_link}")
        playlist = Playlist(playlist_link)
        
        # Load all pages of the playlist
        while playlist.hasMoreVideos:
            playlist.getNextVideos()
        
        return [video['id'] for video in playlist.videos]
    
    except Exception as e:
        logging.error(f"Failed to get playlist videos: {str(e)}")
        return None

def get_channel_video_ids(channel_identifier: str, limit: int = 50) -> Optional[List[str]]:
    """Get video IDs from a YouTube channel."""
    try:
        logging.info(f"Fetching videos from channel: {channel_identifier}")
        channel = Channel(channel_identifier)
        
        # Load videos until we reach the limit
        while channel.hasMoreVideos and len(channel.videos) < limit:
            channel.getNextVideos()
        
        return [video['id'] for video in channel.videos[:limit]]
    
    except Exception as e:
        logging.error(f"Failed to get channel videos: {str(e)}")
        return None
