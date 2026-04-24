package main

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestFetchSRTMatchesHAR(t *testing.T) {
	originalEndpoint := upstreamEndpoint
	defer func() { upstreamEndpoint = originalEndpoint }()

	var gotMethod string
	var gotPath string
	var gotBody string
	var gotHeaders http.Header

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotHeaders = r.Header.Clone()

		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("read request body: %v", err)
		}
		gotBody = string(body)

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status": "READY",
			"data": map[string]any{
				"transcripts": []map[string]string{
					{"t": "Okay. So, today I have someone very very", "s": "0.08", "e": "4.08"},
					{"t": "interesting here. Monday to Friday I", "s": "2.64", "e": "6.64"},
					{"t": "would go to uni 8 to 6 and Saturday", "s": "4.08", "e": "8.48"},
				},
			},
		})
	}))
	defer server.Close()

	upstreamEndpoint = server.URL + "/api/v1/Subtitles"

	srt, err := fetchSRT("https://tubetranscript.com/en/watch?v=NZB0cTo_9lQ", "", time.Second)
	if err != nil {
		t.Fatalf("fetchSRT: %v", err)
	}

	if gotMethod != http.MethodPost {
		t.Fatalf("method = %s, want POST", gotMethod)
	}
	if gotPath != "/api/v1/Subtitles" {
		t.Fatalf("path = %s, want /api/v1/Subtitles", gotPath)
	}
	if gotBody != `{"video_id":"NZB0cTo_9lQ"}` {
		t.Fatalf("body = %s, want HAR video_id payload", gotBody)
	}
	if gotHeaders.Get("Accept") != "*/*" {
		t.Fatalf("Accept = %q, want */*", gotHeaders.Get("Accept"))
	}
	if gotHeaders.Get("Content-Type") != "application/json" {
		t.Fatalf("Content-Type = %q, want application/json", gotHeaders.Get("Content-Type"))
	}
	if gotHeaders.Get("Origin") != "https://tubetranscript.com" {
		t.Fatalf("Origin = %q, want https://tubetranscript.com", gotHeaders.Get("Origin"))
	}
	if gotHeaders.Get("Referer") != "https://tubetranscript.com/" {
		t.Fatalf("Referer = %q, want https://tubetranscript.com/", gotHeaders.Get("Referer"))
	}
	if gotHeaders.Get("User-Agent") == "" {
		t.Fatalf("User-Agent is empty, want non-empty User-Agent")
	}
	if !strings.Contains(gotHeaders.Get("User-Agent"), "Chrome") && !strings.Contains(gotHeaders.Get("User-Agent"), "Firefox") && !strings.Contains(gotHeaders.Get("User-Agent"), "Safari") {
		t.Fatalf("User-Agent = %q, want Chrome, Firefox or Safari UA", gotHeaders.Get("User-Agent"))
	}
	if gotHeaders.Get("X-App-Version") != "1" {
		t.Fatalf("X-App-Version = %q, want 1", gotHeaders.Get("X-App-Version"))
	}
	if gotHeaders.Get("X-Source") != "tubetranscript" {
		t.Fatalf("X-Source = %q, want tubetranscript", gotHeaders.Get("X-Source"))
	}
	if gotHeaders.Get("Sec-Fetch-Dest") != "empty" {
		t.Fatalf("Sec-Fetch-Dest = %q, want empty", gotHeaders.Get("Sec-Fetch-Dest"))
	}
	if gotHeaders.Get("Sec-Fetch-Mode") != "cors" {
		t.Fatalf("Sec-Fetch-Mode = %q, want cors", gotHeaders.Get("Sec-Fetch-Mode"))
	}
	if gotHeaders.Get("Sec-Fetch-Site") != "cross-site" {
		t.Fatalf("Sec-Fetch-Site = %q, want cross-site", gotHeaders.Get("Sec-Fetch-Site"))
	}

	want := strings.Join([]string{
		"1",
		"00:00:00,080 --> 00:00:04,080",
		"Okay. So, today I have someone very very",
		"",
		"2",
		"00:00:02,640 --> 00:00:06,640",
		"interesting here. Monday to Friday I",
		"",
		"3",
		"00:00:04,080 --> 00:00:08,480",
		"would go to uni 8 to 6 and Saturday",
		"",
		"",
	}, "\n")
	if srt != want {
		t.Fatalf("srt mismatch\nwant:\n%s\n---\ngot:\n%s", want, srt)
	}
}

func TestHandleRequestOptionsPreflight(t *testing.T) {
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodOptions, "/api/v1/Subtitles", nil)

	handleRequest(rr, req, time.Second)

	if rr.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want %d", rr.Code, http.StatusNoContent)
	}
	if got := rr.Header().Get("Access-Control-Allow-Origin"); got != "*" {
		t.Fatalf("Access-Control-Allow-Origin = %q, want *", got)
	}
	if got := rr.Header().Get("Access-Control-Allow-Methods"); got != "GET, POST, OPTIONS" {
		t.Fatalf("Access-Control-Allow-Methods = %q, want GET, POST, OPTIONS", got)
	}
	if got := rr.Header().Get("Access-Control-Allow-Headers"); got != "Content-Type, X-App-Version, X-Source" {
		t.Fatalf("Access-Control-Allow-Headers = %q, want Content-Type, X-App-Version, X-Source", got)
	}
	if got := rr.Header().Get("Vary"); got != "Origin" {
		t.Fatalf("Vary = %q, want Origin", got)
	}
}
