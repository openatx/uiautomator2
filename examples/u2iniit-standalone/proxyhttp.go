package main

import (
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/koding/websocketproxy"
)

// TODO(ssx): not tested yet.
type HTTPWSProxy struct {
	forwardedAddr string
	wsProxy       *websocketproxy.WebsocketProxy
	httpProxy     *httputil.ReverseProxy
}

// NewHTTPWSProxy return Proxy instance
func NewHTTPWSProxy(forwardedAddr string) *HTTPWSProxy {
	wsURL, _ := url.Parse("ws://" + forwardedAddr)
	httpURL, _ := url.Parse("http://" + forwardedAddr)

	return &HTTPWSProxy{
		forwardedAddr: forwardedAddr,
		wsProxy:       websocketproxy.NewProxy(wsURL),
		httpProxy:     httputil.NewSingleHostReverseProxy(httpURL),
	}
}

func (p *HTTPWSProxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("Upgrade") == "websocket" {
		log.Println("proxy websocket", r.RequestURI)
		p.wsProxy.ServeHTTP(w, r)
		return
	}
	log.Println("proxy http", r.RequestURI)
	p.httpProxy.ServeHTTP(w, r)
}
