import { YouTubeTranscriptApi } from '@hallelx/youtube-transcript';
import { fetchTranscript as fetchPlus } from 'youtube-transcript-plus';

// Video: "How to use YouTube Transcript API" - very likely to have captions
const VIDEO_ID = 'arj7oStGLkU'; 

async function finalAttempt() {
  console.log(`🕵️ Starting Final Bypass Test for Video: ${VIDEO_ID}\n`);

  // --- Attempt 1: @hallelx with a modern Browser User-Agent ---
  try {
    console.log('--- Attempt 1: @hallelx + Browser Spoofing ---');
    const api = new YouTubeTranscriptApi({
      fetchFn: (url, init) => {
        return fetch(url, {
          ...init,
          headers: {
            ...init?.headers,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
          }
        });
      }
    });
    const transcript = await api.fetch(VIDEO_ID);
    console.log(`✅ SUCCESS! Found ${transcript.snippets.length} snippets.`);
    return; // Stop if we win
  } catch (err) {
    console.log(`❌ Attempt 1 Failed: Your home IP is flagged as a bot.`);
  }

  console.log('\n' + '-'.repeat(40) + '\n');

  // --- Attempt 2: Using a different public proxy (corsproxy.io) ---
  try {
    console.log('--- Attempt 2: @hallelx + corsproxy.io ---');
    const api = new YouTubeTranscriptApi({
      fetchFn: (url, init) => {
        const target = `https://api.corsproxy.io/?url=${encodeURIComponent(url.toString())}`;
        return fetch(target, init);
      }
    });
    const transcript = await api.fetch(VIDEO_ID);
    console.log(`✅ SUCCESS! Found ${transcript.snippets.length} snippets.`);
    return;
  } catch (err) {
    console.log(`❌ Attempt 2 Failed: The proxy is also blocked.`);
  }

  console.log('\n' + '-'.repeat(40) + '\n');

  // --- Attempt 3: youtube-transcript-plus with built-in UA ---
  try {
    console.log('--- Attempt 3: youtube-transcript-plus + UA ---');
    const segments = await fetchPlus(VIDEO_ID, {
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    });
    console.log(`✅ SUCCESS! Found ${segments.length} segments.`);
  } catch (err) {
    console.log(`❌ Attempt 3 Failed.`);
  }
}

finalAttempt().then(() => {
  console.log("\n🏁 Test Complete.");
});
