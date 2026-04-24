package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestLegacyMainMatchesHAR(t *testing.T) {
	originalEndpoint := legacyUpstreamEndpoint
	defer func() { legacyUpstreamEndpoint = originalEndpoint }()

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
				},
			},
		})
	}))
	defer server.Close()

	legacyUpstreamEndpoint = server.URL + "/api/v1/Subtitles"

	origArgs := os.Args
	origFlags := flag.CommandLine
	defer func() {
		os.Args = origArgs
		flag.CommandLine = origFlags
	}()

	flag.CommandLine = flag.NewFlagSet("yt-transcript-proxy", flag.ContinueOnError)
	flag.CommandLine.SetOutput(io.Discard)
	os.Args = []string{"yt-transcript-proxy", "-id", "NZB0cTo_9lQ"}

	stdout := os.Stdout
	stderr := os.Stderr
	outR, outW, err := os.Pipe()
	if err != nil {
		t.Fatalf("stdout pipe: %v", err)
	}
	errR, errW, err := os.Pipe()
	if err != nil {
		t.Fatalf("stderr pipe: %v", err)
	}
	os.Stdout = outW
	os.Stderr = errW
	defer func() {
		os.Stdout = stdout
		os.Stderr = stderr
	}()

	var outBuf bytes.Buffer
	var errBuf bytes.Buffer
	stdoutDone := make(chan struct{})
	stderrDone := make(chan struct{})
	go func() {
		_, _ = io.Copy(&outBuf, outR)
		close(stdoutDone)
	}()
	go func() {
		_, _ = io.Copy(&errBuf, errR)
		close(stderrDone)
	}()

	main()

	_ = outW.Close()
	_ = errW.Close()
	<-stdoutDone
	<-stderrDone

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
	if gotHeaders.Get("User-Agent") != "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36" {
		t.Fatalf("User-Agent = %q, want HAR UA", gotHeaders.Get("User-Agent"))
	}
	if gotHeaders.Get("X-App-Version") != "1" {
		t.Fatalf("X-App-Version = %q, want 1", gotHeaders.Get("X-App-Version"))
	}
	if gotHeaders.Get("X-Source") != "tubetranscript" {
		t.Fatalf("X-Source = %q, want tubetranscript", gotHeaders.Get("X-Source"))
	}
	if errBuf.Len() != 0 {
		t.Fatalf("stderr = %q, want empty", errBuf.String())
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
		"",
	}, "\n")
	if outBuf.String() != want {
		t.Fatalf("stdout mismatch\nwant:\n%s\n---\ngot:\n%s", want, outBuf.String())
	}
}
