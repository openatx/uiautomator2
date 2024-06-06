/*
Copyright © 2024 NAME HERE <EMAIL ADDRESS>
*/
package cmd

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/spf13/cobra"
)

// httpcheckCmd represents the httpcheck command
var httpcheckCmd = &cobra.Command{
	Use:   "httpcheck",
	Short: "check if network is available by sending a http request",
	Run:   httpcheckRun,
}

func init() {
	rootCmd.AddCommand(httpcheckCmd)

	httpcheckCmd.Flags().StringP("dns", "d", "114.114.114.114", "DNS resolver")
}

func httpcheckRun(_ *cobra.Command, args []string) {
	fmt.Println("httpcheck called")
	doHttpCheck()
}

// Function to check a single site with specific DNS and timeout settings
func checkSite(url string, wg *sync.WaitGroup, resultChan chan<- bool, dnsResolver string, httpTimeout time.Duration) {
	defer wg.Done()

	// Append default DNS port if not specified
	if !strings.Contains(dnsResolver, ":") {
		dnsResolver += ":53"
	}

	// Custom dialer with specific DNS resolver
	dialer := &net.Dialer{
		Timeout: httpTimeout,
		Resolver: &net.Resolver{
			PreferGo: true,
			Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
				d := net.Dialer{
					Timeout: httpTimeout,
				}
				return d.DialContext(ctx, "udp", dnsResolver)
			},
		},
	}

	// HTTP client using the custom transport with dialer
	client := http.Client{
		Timeout: httpTimeout,
		Transport: &http.Transport{
			DialContext: dialer.DialContext,
			TLSClientConfig: &tls.Config{
				InsecureSkipVerify: true, // Skip SSL certificate verification
			},
		},
	}

	// Perform HTTP GET request
	resp, err := client.Get(url)
	if err != nil {
		fmt.Println("Error checking:", url, err)
		resultChan <- false
		return
	}
	defer resp.Body.Close()

	// Check HTTP status
	if resp.StatusCode == http.StatusOK {
		fmt.Println(url, "is up.")
		resultChan <- true
	} else {
		fmt.Println(url, "status code:", resp.StatusCode)
		resultChan <- false
	}
}

func doHttpCheck() {
	var wg sync.WaitGroup
	resultChan := make(chan bool, 3) // Buffer for 3 results

	// Command-line flags
	var dnsResolver string = "114.114.114.114"
	var timeoutSec int = 3
	var urls = []string{"https://taobao.com", "https://qq.com", "https://baidu.com", "https://www.example.com"}

	// Convert timeout to time.Duration
	httpTimeout := time.Duration(timeoutSec) * time.Second

	// URLs to check
	for _, url := range urls {
		wg.Add(1)
		go checkSite(url, &wg, resultChan, dnsResolver, httpTimeout)
	}

	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Evaluate results
	networkOK := false
	for result := range resultChan {
		if result {
			networkOK = true
			break
		}
	}

	if networkOK {
		fmt.Println("network=true")
	} else {
		fmt.Println("network=false")
	}
}
