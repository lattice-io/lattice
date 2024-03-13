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
	"strconv"
)

type LokiQueryResponse struct {
	Status string           `json:"status"`
	Data   LokiResponseData `json:"data"`
}

type LokiResponseData struct {
	ResultType string            `json:"resultType"`
	Result     []LokiStreamEntry `json:"result"`
}

type LokiStreamEntry struct {
	Stream map[string]string `json:"stream"`
	Values []LokiLogLine     `json:"values"`
}

type LokiLogLine struct {
	Time int64  `json:"time"` // unix nanosecond epoch
	Log  string `json:"log"`
}

type LokiLogEntry struct {
	Log string `json:"log"`
}

func (l *LokiLogLine) UnmarshalJSON(p []byte) error {
	var tmp []interface{}
	if err := json.Unmarshal(p, &tmp); err != nil {
		return err
	}

	// Parse time string
	timeStr := tmp[0].(string)
	timeInt64, err := strconv.ParseInt(timeStr, 10, 64)
	if err != nil {
		return err
	}
	l.Time = timeInt64

	// Parse log string
	logStr := tmp[1].(string)
	var logEntry LokiLogEntry
	if err := json.Unmarshal([]byte(logStr), &logEntry); err != nil {
		return err
	}
	l.Log = logEntry.Log

	return nil
}

// Log line we sent in a response
// Compared with LokiLogLine, we add Pod field
type LokiResponseLogLine struct {
	Time int64  `json:"time"` // unix nanosecond epoch
	Log  string `json:"log"`
	Pod  string `json:"pod"`
}

// a list of LokiResponseLogLine
type LokiLog []LokiResponseLogLine

type LokiLogResponse struct {
	Log LokiLog `json:"log"`
}
