package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"math"
	"os"
	"strings"
)

type SubtitleRequest struct {
	VideoID string `json:"video_id"`
}

type SubtitleEntry struct {
	Text  string `json:"t"`
	Start string `json:"s"`
	End   string `json:"e"`
}

type SubtitleResponse struct {
	Status string `json:"status"`
	Data   struct {
		Transcripts []SubtitleEntry `json:"transcripts"`
	} `json:"data"`
}

var legacyUpstreamEndpoint = "https://yt-to-text.com/api/v1/Subtitles"

func main() {
	videoID := flag.String("id", "", "YouTube video ID")
	flag.Parse()

	if *videoID == "" {
		fmt.Fprintln(os.Stderr, "Usage: yt-transcript-proxy -id VIDEO_ID")
		os.Exit(1)
	}

	reqBody, _ := json.Marshal(SubtitleRequest{VideoID: *videoID})
	req, _ := http.NewRequest("POST", legacyUpstreamEndpoint, bytes.NewBuffer(reqBody))
	req.Header.Set("Accept", "*/*")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Origin", "https://tubetranscript.com")
	req.Header.Set("Referer", "https://tubetranscript.com/")
	req.Header.Set("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")
	req.Header.Set("x-app-version", "1")
	req.Header.Set("x-source", "tubetranscript")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	
	var result SubtitleResponse
	if err := json.Unmarshal(body, &result); err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing response: %v\n", err)
		os.Exit(1)
	}

	for i, sub := range result.Data.Transcripts {
		fmt.Printf("%d\n", i+1)
		fmt.Printf("%s --> %s\n", formatTime(sub.Start), formatTime(sub.End))
		fmt.Printf("%s\n\n", strings.TrimSpace(sub.Text))
	}
}

func formatTime(seconds string) string {
	var s float64
	fmt.Sscanf(seconds, "%f", &s)
	msTotal := int64(math.Round(s * 1000))
	h := msTotal / 3_600_000
	msTotal %= 3_600_000
	m := msTotal / 60_000
	msTotal %= 60_000
	sec := msTotal / 1000
	ms := msTotal % 1000
	return fmt.Sprintf("%02d:%02d:%02d,%03d", h, m, sec, ms)
}
