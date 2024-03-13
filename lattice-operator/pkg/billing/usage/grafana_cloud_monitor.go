// Copyright 2023 The BreezeML Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package usage

import (
	"bytes"
	"fmt"
	"net/http"

	//lint:ignore SA1019 I have to use the deprecated proto here because the new one is not compatible with prometheus
	"github.com/golang/protobuf/proto" //nolint:all
	"github.com/golang/snappy"
	"github.com/prometheus/common/config"
	"github.com/prometheus/prometheus/prompb"
)

// The following variables are set at build time.
var (
	GrafanaCloudURL      string
	GrafanaCloudUserName string
	GrafanaCloudPassword string
)

type GrafanaCloudMonitor struct {
	AbstractMonitor
	url    string
	cfg    *config.HTTPClientConfig
	client *http.Client
}

func NewGrafanaCloudMonitor() *GrafanaCloudMonitor {
	// configure the client to use basic auth
	cfg := &config.HTTPClientConfig{
		BasicAuth: &config.BasicAuth{
			Username: GrafanaCloudUserName,
			Password: config.Secret(GrafanaCloudPassword),
		},
	}

	// initialize the client
	client, err := config.NewClientFromConfig(*cfg, "grafana_cloud_monitor")
	if err != nil {
		return nil
	}

	return &GrafanaCloudMonitor{cfg: cfg, client: client, url: GrafanaCloudURL}
}

// push timeSeries using the prometheus remote_write API
func (g *GrafanaCloudMonitor) PushMetric(timeSeries []prompb.TimeSeries) error {
	// We submit data to Grafana Cloud's prometheus remote_write protocol endpoint.
	// The endpoint expects a snappy-compressed protobuf message.
	// The read and write protocols both use a snappy-compressed protocol buffer encoding
	// over HTTP. The protocols are not considered as stable APIs yet and may change to use
	// gRPC over HTTP/2 in the future, when all hops between Prometheus and the remote
	// storage can safely be assumed to support HTTP/2.
	// For more information, see:
	// https://prometheus.io/docs/operating/integrations/#remote-endpoints-and-storage
	// https://github.com/prometheus/prometheus/blob/main/prompb/remote.proto

	//Create the write request
	writeReq := &prompb.WriteRequest{
		Timeseries: timeSeries,
	}

	// use proto to serialize the request
	data, err := proto.Marshal(writeReq)
	if err != nil {
		return err
	}

	// encode the request
	encoded := snappy.Encode(nil, data)
	body := bytes.NewReader(encoded)
	// construct the request
	req, err := http.NewRequest("POST", g.url, body)
	if err != nil {
		return err
	}

	// set the headers
	req.Header.Set("Content-Encoding", "snappy")
	req.Header.Set("Content-Type", "application/x-protobuf")
	req.Header.Set("X-Prometheus-Remote-Write-Version", "0.1.0")

	// send the request
	resp, err := g.client.Do(req)
	if err != nil {
		return err
	}

	// check the response
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("server returned HTTP status %s", resp.Status)
	}

	return nil
}
