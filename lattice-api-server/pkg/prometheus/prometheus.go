// Copyright 2022 The BreezeML Authors
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

package prometheus

import (
	"encoding/json"
	"fmt"
	"io"
	"lattice-api-server/pkg/util"
	"net/http"
	"sort"
	"time"
)

const (
	prometheusEndpointEnv = "PROMETHEUS_ENDPOINT"
	queryRangeEnv         = "PROMETHEUS_QUERY_RANGE"
	queryResolutionEnv    = "PROMETHEUS_QUERY_RESOLUTION"
	prometheusMetricName  = "training_operator_running_pods_total"
	prometheusApiPath     = "/api/v1/query"
	prometheusTimeout     = 4 // default time out of prometheus http request in seconds
	prometheusProtocol    = "http"
)

// get the prometheus endpoint
// by default "prometheus-server"
func getPrometheusEndpoint() string {
	return util.GetEnvWithDefault(prometheusEndpointEnv, "prometheus-server")
}

// get the query range
// by default "72h"
func getQueryRange() string {
	return util.GetEnvWithDefault(queryRangeEnv, "72h")
}

// get the query resolution
// by default "1m"
func getQueryResolution() string {
	return util.GetEnvWithDefault(queryResolutionEnv, "1m")
}

// this function fetches time series for all trainingjobs from prometheus
func fetchPrometheusTimeSeries(endpoint string, queryRange string, queryResolution string) (PrometheusMatrixData, error) {
	// Initialize client and request
	client := http.Client{Timeout: prometheusTimeout * time.Second}
	url := prometheusProtocol + "://" + endpoint + prometheusApiPath
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return PrometheusMatrixData{}, err
	}

	// Prepare query
	query := fmt.Sprintf("%s[%s:%s]", prometheusMetricName, queryRange, queryResolution)
	q := req.URL.Query()
	q.Add("query", query)
	req.URL.RawQuery = q.Encode()

	// Send the request
	resp, err := client.Do(req)
	if err != nil {
		return PrometheusMatrixData{}, err
	}
	defer resp.Body.Close()

	// Parse the data
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return PrometheusMatrixData{}, err
	}

	prometheusResp := new(PrometheusMatrixResponse)
	err = json.Unmarshal(body, prometheusResp)
	if err != nil {
		return PrometheusMatrixData{}, err
	}

	return prometheusResp.Data, nil
}

// this function fetches time series for all trainingjobs from prometheus,
// classify them based on their job uids,
// and sort them based on time
func FetchTimeSeries(jobNameToUIDMap map[string]string) (TimeSeries, error) {
	endpoint := getPrometheusEndpoint()
	queryRange := getQueryRange()
	queryResolution := getQueryResolution()

	data, err := fetchPrometheusTimeSeries(endpoint, queryRange, queryResolution)
	if err != nil {
		return TimeSeries{}, err
	}

	// map {job_uid -> list of prometheus values}
	result := make(TimeSeries)
	for _, metric := range data.Result {
		jobName := metric.Metric["job_id"]
		if jobUID, ok := jobNameToUIDMap[jobName]; ok {
			if _, uidFound := result[jobUID]; !uidFound {
				result[jobUID] = []PrometheusValue{}
			}
			result[jobUID] = append(result[jobUID], metric.Values...)
		}
	}

	// sort all events based on time
	for key := range result {
		sort.Slice(result[key], func(i, j int) bool {
			return result[key][i].Time < result[key][j].Time
		})
	}

	return result, nil
}

// this function filters out timepoints before the given start time
// also make sure that we only keep those timepoints where there is a change in the value
func FilterTimeSeries(timeSeries *[]PrometheusValue, startTime float64) []PrometheusValue {
	result := []PrometheusValue{}
	for _, value := range *timeSeries {
		if value.Time >= startTime {
			result = append(result, value)
		}
	}

	// make a bool slice marking which timepoints to keep
	// keep the first timepoint
	keep := make([]bool, len(result))
	for i := range keep {
		keep[i] = false
	}

	keep[0] = true

	// make sure that we only keep those timepoints where there is a change in the value
	for i := 0; i < len(result)-1; i++ {
		if result[i].Value != result[i+1].Value {
			keep[i] = true
			keep[i+1] = true
		}
	}

	// keep the last timepoint
	keep[len(result)-1] = true

	// filter out timepoints
	filteredResult := []PrometheusValue{}
	for i := 0; i < len(result); i++ {
		if keep[i] {
			filteredResult = append(filteredResult, result[i])
		}
	}

	return filteredResult
}
