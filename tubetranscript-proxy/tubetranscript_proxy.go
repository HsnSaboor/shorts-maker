package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"math"
	"math/rand"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var upstreamEndpoint = "https://yt-to-text.com/api/v1/Subtitles"

var rawVideoID = regexp.MustCompile(`^[A-Za-z0-9_-]{11}$`)

var userAgents = []string{
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
	"Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/146.0.3856.109 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
}

var platforms = []string{"\"Windows\"", "\"macOS\"", "\"Linux\"", "\"Android\""}
var telemetryProfiles = []map[string]string{
	{
		"Sec-Fetch-Dest":  "empty",
		"Sec-Fetch-Mode":  "cors",
		"Sec-Fetch-Site":  "cross-site",
		"Accept-Language": "en-US,en;q=0.9",
		"X-Client-Data":   "CIa2ywE=",
	},
	{
		"Sec-Fetch-Dest":  "empty",
		"Sec-Fetch-Mode":  "cors",
		"Sec-Fetch-Site":  "cross-site",
		"Accept-Language": "en-GB,en;q=0.8",
		"X-Client-Data":   "CJ+2ywE=",
	},
	{
		"Sec-Fetch-Dest":  "empty",
		"Sec-Fetch-Mode":  "cors",
		"Sec-Fetch-Site":  "cross-site",
		"Accept-Language": "fr-FR,fr;q=0.9",
		"X-Client-Data":   "CKa2ywE=",
	},
	{
		"Sec-Fetch-Dest":  "empty",
		"Sec-Fetch-Mode":  "cors",
		"Sec-Fetch-Site":  "cross-site",
		"Accept-Language": "de-DE,de;q=0.9",
		"X-Client-Data":   "CLa2ywE=",
	},
	{
		"Sec-Fetch-Dest":  "empty",
		"Sec-Fetch-Mode":  "cors",
		"Sec-Fetch-Site":  "cross-site",
		"Accept-Language": "es-ES,es;q=0.9",
		"X-Client-Data":   "CMa2ywE=",
	},
	{
		"Sec-Fetch-Dest":  "empty",
		"Sec-Fetch-Mode":  "cors",
		"Sec-Fetch-Site":  "cross-site",
		"Accept-Language": "ja-JP,ja;q=0.9",
		"X-Client-Data":   "CNa2ywE=",
	},
	{
		"Sec-Fetch-Dest":  "empty",
		"Sec-Fetch-Mode":  "cors",
		"Sec-Fetch-Site":  "cross-site",
		"Accept-Language": "zh-CN,zh;q=0.9",
		"X-Client-Data":   "COa2ywE=",
	},
	{
		"Sec-Fetch-Dest":  "empty",
		"Sec-Fetch-Mode":  "cors",
		"Sec-Fetch-Site":  "cross-site",
		"Accept-Language": "pt-BR,pt;q=0.9",
		"X-Client-Data":   "CPa2ywE=",
	},
}
var timezones = []string{
	"America/New_York", "Europe/London", "Asia/Karachi", "Asia/Tokyo", "Europe/Paris",
	"America/Los_Angeles", "America/Chicago", "America/Denver", "Europe/Berlin", "Asia/Dubai",
	"Asia/Shanghai", "Australia/Sydney", "Europe/Moscow", "America/Sao_Paulo", "Africa/Johannesburg",
	"Asia/Singapore", "Europe/Rome", "Asia/Kolkata", "America/Toronto", "Europe/Amsterdam",
}
var utcOffsets = []string{
	"-300", "-240", "-180", "300", "540", "0", "60", "120", "-360", "-420", "180", "360", "480", "720",
	"660", "420", "240", "-120", "600", "780",
}

var httpClient = &http.Client{
	Jar: nil,
	Timeout: 20 * time.Second,
}

func init() {
	jar, _ := cookiejar.New(nil)
	httpClient.Jar = jar
}

type inputPayload struct {
	URL      string `json:"url"`
	VideoURL string `json:"videoUrl"`
	ID       string `json:"id"`
	VideoID  string `json:"video_id"`
}

type upstreamTranscriptResponse struct {
	Status string `json:"status"`
	Data   struct {
		Transcripts []transcriptLine `json:"transcripts"`
	} `json:"data"`
}

type transcriptLine struct {
	Text  string `json:"t"`
	Start string `json:"s"`
	End   string `json:"e"`
}

type transcriptOutput struct {
	Transcripts []transcriptLine `json:"transcripts"`
}

func main() {
	listen := flag.String("listen", ":8080", "listen address for HTTP mode")
	urlInput := flag.String("url", "", "YouTube URL to convert")
	idInput := flag.String("id", "", "YouTube video ID to convert")
	format := flag.String("format", "srt", "output format: srt, vtt, json, txt")
	output := flag.String("output", "", "output file (default: stdout)")
	timeout := flag.Duration("timeout", 20*time.Second, "upstream request timeout")
	flag.Parse()

	if *urlInput != "" || *idInput != "" {
		data, err := fetchTranscripts(*urlInput, *idInput, *timeout)
		if err != nil {
			fatal(err)
		}
		outputStr, err := formatTranscripts(data, *format)
		if err != nil {
			fatal(err)
		}
		if *output != "" {
			if err := os.WriteFile(*output, []byte(outputStr), 0644); err != nil {
				fatal(err)
			}
			log.Printf("output written to %s", *output)
		} else {
			fmt.Print(outputStr)
		}
		return
	}

	mux := http.NewServeMux()
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handleRequest(w, r, *timeout)
	})
	mux.Handle("/", handler)
	mux.Handle("/srt", handler)
	mux.Handle("/api/v1/Subtitles", handler)

	server := &http.Server{
		Addr:              *listen,
		Handler:           cors(mux),
		ReadHeaderTimeout: 10 * time.Second,
	}

	log.Printf("listening on %s", *listen)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		fatal(err)
	}
}

func handleRequest(w http.ResponseWriter, r *http.Request, timeout time.Duration) {
	setCORSHeaders(w)

	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	videoURL, videoID, err := readInput(r)
	if err != nil {
		writeHTTPError(w, http.StatusBadRequest, err)
		return
	}

	if videoURL == "" && videoID == "" {
		if r.URL.Path == "/" {
			writeDocs(w)
			return
		}
		writeHTTPError(w, http.StatusBadRequest, errors.New("provide ?url=... or ?id=... or POST JSON {\"video_id\":...}"))
		return
	}

	transcripts, err := fetchTranscripts(videoURL, videoID, timeout)
	if err != nil {
		writeHTTPError(w, http.StatusBadGateway, err)
		return
	}

	format := r.URL.Query().Get("format")
	if format == "" {
		format = "srt"
	}

	output, err := formatTranscripts(transcripts, format)
	if err != nil {
		writeHTTPError(w, http.StatusBadRequest, err)
		return
	}

	contentType := getContentType(format)
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Cache-Control", "no-store")
	_, _ = io.WriteString(w, output)
}

func getContentType(format string) string {
	switch strings.ToLower(format) {
	case "srt":
		return "text/plain; charset=utf-8"
	case "vtt":
		return "text/vtt; charset=utf-8"
	case "json":
		return "application/json; charset=utf-8"
	case "txt":
		return "text/plain; charset=utf-8"
	default:
		return "text/plain; charset=utf-8"
	}
}

func readInput(r *http.Request) (string, string, error) {
	q := r.URL.Query()
	videoURL := firstNonEmpty(
		q.Get("url"),
		q.Get("video_url"),
		q.Get("videoUrl"),
	)
	videoID := firstNonEmpty(
		q.Get("id"),
		q.Get("video_id"),
	)

	if r.Method != http.MethodPost && r.Method != http.MethodPut && r.Method != http.MethodPatch {
		return videoURL, videoID, nil
	}

	ct := r.Header.Get("Content-Type")
	if !strings.Contains(strings.ToLower(ct), "application/json") && ct != "" {
		return videoURL, videoID, nil
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		return "", "", err
	}
	if len(bytes.TrimSpace(body)) == 0 {
		return videoURL, videoID, nil
	}

	var in inputPayload
	if err := json.Unmarshal(body, &in); err != nil {
		return "", "", err
	}

	videoURL = firstNonEmpty(videoURL, in.URL, in.VideoURL)
	videoID = firstNonEmpty(videoID, in.ID, in.VideoID)
	return videoURL, videoID, nil
}

func applyAntiBanHeaders(req *http.Request) {
	ua := userAgents[rand.Intn(len(userAgents))]
	platform := platforms[rand.Intn(len(platforms))]
	chromeVer := extractChromeVersion(ua)
	tz := timezones[rand.Intn(len(timezones))]
	utcOffset := utcOffsets[rand.Intn(len(utcOffsets))]
	profile := telemetryProfiles[rand.Intn(len(telemetryProfiles))]

	req.Header.Set("Accept", "*/*")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Origin", "https://tubetranscript.com")
	req.Header.Set("Referer", "https://tubetranscript.com/")
	req.Header.Set("User-Agent", ua)
	req.Header.Set("X-App-Version", "1")
	req.Header.Set("X-Source", "tubetranscript")

	if chromeVer != "" {
		req.Header.Set("sec-ch-ua", fmt.Sprintf("\"Google Chrome\";v=\"%s\", \"Not.A/Brand\";v=\"8\", \"Chromium\";v=\"%s\"", chromeVer, chromeVer))
	}
	req.Header.Set("sec-ch-ua-mobile", "?0")
	req.Header.Set("sec-ch-ua-platform", platform)
	req.Header.Set("Sec-Fetch-Dest", profile["Sec-Fetch-Dest"])
	req.Header.Set("Sec-Fetch-Mode", profile["Sec-Fetch-Mode"])
	req.Header.Set("Sec-Fetch-Site", profile["Sec-Fetch-Site"])
	req.Header.Set("Accept-Language", profile["Accept-Language"])
	req.Header.Set("X-YouTube-Utc-Offset", utcOffset)
	req.Header.Set("X-YouTube-Time-Zone", tz)
	req.Header.Set("X-YouTube-Device", fmt.Sprintf("cbr=Chrome&cbrver=%s&ceng=WebKit&cengver=537.36&cos=%s&cplatform=DESKTOP", chromeVer, strings.Trim(platform, "\"")))
	req.Header.Set("X-Goog-Request-Time", fmt.Sprintf("%d", time.Now().UnixMilli()))
}

func extractChromeVersion(ua string) string {
	re := regexp.MustCompile(`Chrome/([0-9.]+)`)
	if m := re.FindStringSubmatch(ua); len(m) > 1 {
		parts := strings.Split(m[1], ".")
		if len(parts) > 0 {
			return parts[0]
		}
	}
	return "147"
}

func randomJitter() {
	time.Sleep(time.Duration(rand.Intn(500)+200) * time.Millisecond)
}

func fetchTranscripts(videoURL, videoID string, timeout time.Duration) ([]transcriptLine, error) {
	id, err := resolveVideoID(videoURL, videoID)
	if err != nil {
		return nil, err
	}

	payload, err := json.Marshal(map[string]string{"video_id": id})
	if err != nil {
		return nil, err
	}

	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(attempt*attempt) * 500 * time.Millisecond)
		}

		req, err := http.NewRequest(http.MethodPost, upstreamEndpoint, bytes.NewReader(payload))
		if err != nil {
			return nil, err
		}

		applyAntiBanHeaders(req)
		randomJitter()

		httpClient.Timeout = timeout
		resp, err := httpClient.Do(req)
		if err != nil {
			lastErr = err
			continue
		}
		defer resp.Body.Close()

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			lastErr = err
			continue
		}
		if resp.StatusCode != http.StatusOK {
			lastErr = fmt.Errorf("upstream returned %s: %s", resp.Status, strings.TrimSpace(string(body)))
			if resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode == http.StatusForbidden {
				continue
			}
			return nil, lastErr
		}

		var out upstreamTranscriptResponse
		if err := json.Unmarshal(body, &out); err != nil {
			return nil, err
		}

		if len(out.Data.Transcripts) == 0 {
			return nil, fmt.Errorf("upstream returned no transcripts for %s", id)
		}

		return out.Data.Transcripts, nil
	}

	return nil, fmt.Errorf("failed after 3 attempts: %v", lastErr)
}

func formatTranscripts(transcripts []transcriptLine, format string) (string, error) {
	switch strings.ToLower(format) {
	case "srt":
		return transcriptsToSRT(transcripts), nil
	case "vtt":
		return transcriptsToVTT(transcripts), nil
	case "json":
		return transcriptsToJSON(transcripts), nil
	case "txt":
		return transcriptsToTXT(transcripts), nil
	default:
		return "", fmt.Errorf("unsupported format: %s (supported: srt, vtt, json, txt)", format)
	}
}

func transcriptsToSRT(lines []transcriptLine) string {
	var b strings.Builder
	index := 1

	for _, line := range lines {
		start, err := parseSeconds(line.Start)
		if err != nil {
			continue
		}
		end, err := parseSeconds(line.End)
		if err != nil {
			continue
		}

		startMs := secondsToMillis(start)
		endMs := secondsToMillis(end)
		if endMs <= startMs {
			endMs = startMs + 1
		}

		text := normalizeText(line.Text)
		if text == "" {
			continue
		}

		fmt.Fprintf(&b, "%d\n%s --> %s\n%s\n\n", index, formatMillis(startMs), formatMillis(endMs), text)
		index++
	}

	return b.String()
}

func transcriptsToVTT(lines []transcriptLine) string {
	var b strings.Builder
	b.WriteString("WEBVTT\n\n")

	for _, line := range lines {
		start, err := parseSeconds(line.Start)
		if err != nil {
			continue
		}
		end, err := parseSeconds(line.End)
		if err != nil {
			continue
		}

		startMs := secondsToMillis(start)
		endMs := secondsToMillis(end)
		if endMs <= startMs {
			endMs = startMs + 1
		}

		text := normalizeText(line.Text)
		if text == "" {
			continue
		}

		fmt.Fprintf(&b, "%s --> %s\n%s\n\n", formatVTTTime(startMs), formatVTTTime(endMs), text)
	}

	return b.String()
}

func transcriptsToJSON(lines []transcriptLine) string {
	data := transcriptOutput{Transcripts: lines}
	jsonData, _ := json.MarshalIndent(data, "", "  ")
	return string(jsonData) + "\n"
}

func transcriptsToTXT(lines []transcriptLine) string {
	var b strings.Builder
	for _, line := range lines {
		text := normalizeText(line.Text)
		if text == "" {
			continue
		}
		b.WriteString(text)
		b.WriteString(" ")
	}
	return strings.TrimSpace(b.String())
}

func formatVTTTime(ms int64) string {
	if ms < 0 {
		ms = 0
	}
	hours := ms / 3_600_000
	ms %= 3_600_000
	minutes := ms / 60_000
	ms %= 60_000
	seconds := ms / 1000
	ms %= 1000
	return fmt.Sprintf("%02d:%02d:%02d.%03d", hours, minutes, seconds, ms)
}

func normalizeText(s string) string {
	return strings.Join(strings.Fields(strings.TrimSpace(s)), " ")
}

func parseSeconds(s string) (float64, error) {
	return strconv.ParseFloat(strings.TrimSpace(s), 64)
}

func secondsToMillis(seconds float64) int64 {
	if seconds < 0 {
		seconds = 0
	}
	return int64(math.Round(seconds * 1000))
}

func formatMillis(ms int64) string {
	if ms < 0 {
		ms = 0
	}
	hours := ms / 3_600_000
	ms %= 3_600_000
	minutes := ms / 60_000
	ms %= 60_000
	seconds := ms / 1000
	ms %= 1000
	return fmt.Sprintf("%02d:%02d:%02d,%03d", hours, minutes, seconds, ms)
}

func resolveVideoID(videoURL, videoID string) (string, error) {
	videoURL = strings.TrimSpace(videoURL)
	videoID = strings.TrimSpace(videoID)

	if videoURL == "" && videoID == "" {
		return "", errors.New("missing video id or youtube url")
	}

	extracted := ""
	if videoURL != "" {
		extracted = extractVideoID(videoURL)
		if extracted == "" {
			return "", fmt.Errorf("could not extract a youtube video id from %q", videoURL)
		}
	}

	if videoID != "" && extracted != "" && videoID != extracted {
		return "", fmt.Errorf("id %q does not match url video id %q", videoID, extracted)
	}

	if videoID != "" {
		return videoID, nil
	}
	return extracted, nil
}

func extractVideoID(input string) string {
	input = strings.TrimSpace(input)
	if input == "" {
		return ""
	}

	if rawVideoID.MatchString(input) {
		return input
	}

	if u, err := url.Parse(input); err == nil && u != nil {
		if v := u.Query().Get("v"); v != "" {
			return v
		}

		path := strings.Trim(u.Path, "/")
		if path != "" {
			parts := strings.Split(path, "/")
			for i := len(parts) - 1; i >= 0; i-- {
				part := strings.TrimSpace(parts[i])
				if part == "" || part == "watch" || part == "embed" || part == "shorts" || part == "live" {
					continue
				}
				if rawVideoID.MatchString(part) {
					return part
				}
			}
		}
	}

	if m := regexp.MustCompile(`(?:v=|youtu\.be/|embed/|shorts/|live/)([A-Za-z0-9_-]{11})`).FindStringSubmatch(input); len(m) == 2 {
		return m[1]
	}

	return ""
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if s := strings.TrimSpace(v); s != "" {
			return s
		}
	}
	return ""
}

func writeDocs(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = io.WriteString(w, "Use GET /api/v1/Subtitles?id=NZB0cTo_9lQ or GET /api/v1/Subtitles?url=https://www.youtube.com/watch?v=NZB0cTo_9lQ\nPOST JSON {\"video_id\":\"NZB0cTo_9lQ\"} also works.\n")
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		setCORSHeaders(w)
		next.ServeHTTP(w, r)
	})
}

func setCORSHeaders(w http.ResponseWriter) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-App-Version, X-Source")
	w.Header().Set("Access-Control-Expose-Headers", "*")
	if w.Header().Get("Vary") == "" {
		w.Header().Set("Vary", "Origin")
	}
}

func writeHTTPError(w http.ResponseWriter, status int, err error) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(status)
	_, _ = io.WriteString(w, err.Error()+"\n")
}

func fatal(err error) {
	_, _ = fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
