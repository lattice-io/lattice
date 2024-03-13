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

package loki

import (
	"encoding/json"
	"fmt"
	"io"
	"lattice-api-server/pkg/types"
	"lattice-api-server/pkg/util"
	"net/http"
	"sort"
	"time"
)

const (
	lokiEndpointEnv = "LOKI_ENDPOINT"
	lokiLimitEnv    = "LOKI_LIMIT"

	lokiApiPath = "/loki/api/v1/query_range"

	lokiTimeout  = 4 // default time out of loki http request in seconds
	lokiProtocol = "http"
)

// get the loki endpoint
// by default "loki-gateway"
func getLokiEndpoint() string {
	return util.GetEnvWithDefault(lokiEndpointEnv, "loki-gateway")
}

// get the loki limit
// by default 5000
func getLokiLimit() string {
	return util.GetEnvWithDefault(lokiLimitEnv, "5000")
}

// this function fetches logs from a trainingjob from loki
// startTime is the unix nanosecond epoch
func fetchLokiLogResponse(endpoint string, namespace string, name string, startTime int64) (LokiResponseData, error) {
	// Initialize client and request
	client := http.Client{Timeout: lokiTimeout * time.Second}
	url := lokiProtocol + "://" + endpoint + lokiApiPath
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return LokiResponseData{}, err
	}

	// Prepare query
	query := fmt.Sprintf("{namespace=\"%s\",pod=~\"%s.*\"}", namespace, name)
	start := fmt.Sprintf("%d", startTime)
	limit := getLokiLimit()

	q := req.URL.Query()
	q.Add("query", query)
	q.Add("start", start)
	q.Add("limit", limit)

	req.URL.RawQuery = q.Encode()

	// Send the request
	resp, err := client.Do(req)
	if err != nil {
		return LokiResponseData{}, err
	}
	defer resp.Body.Close()

	// Parse the data
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return LokiResponseData{}, err
	}

	lokiResp := new(LokiQueryResponse)
	err = json.Unmarshal(body, lokiResp)
	if err != nil {
		return LokiResponseData{}, err
	}

	return lokiResp.Data, nil
}

// this function fetches logs for a trainingjob from loki
func FetchLokiLogs(job *types.TrainingJob) (LokiLog, error) {
	// Get the endpoint
	endpoint := getLokiEndpoint()

	// Get the unix nanosecond epoch for job.Status.SubmitTime
	startTime := job.Status.SubmitTime.UnixNano()

	// Fetch the logs
	resp, err := fetchLokiLogResponse(endpoint, job.Namespace, job.Name, startTime)
	if err != nil {
		return LokiLog{}, err
	}

	result := make(LokiLog, 0)
	for _, log := range resp.Result {
		if podName, ok := log.Stream["pod"]; !ok {
			continue
		} else {
			for _, logLine := range log.Values {
				result = append(result, LokiResponseLogLine{
					Time: logLine.Time,
					Log:  logLine.Log,
					Pod:  podName,
				})
			}
		}
	}

	// Sort the logs by time (ascending)
	sort.Slice(result, func(i, j int) bool {
		if result[i].Time == result[j].Time {
			return result[i].Pod < result[j].Pod
		} else {
			return result[i].Time < result[j].Time
		}
	})

	return result, nil
}
