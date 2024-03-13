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
	"fmt"
	"os"
	"time"

	trainingoperatorcommon "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/common"
	"github.com/prometheus/prometheus/prompb"
)

const (
	licenseEnv = "LATTICE_LICENSE"
)

// Helper function to get the license from the environment
func getLicense() (string, error) {
	license, ok := os.LookupEnv(licenseEnv)
	if !ok {
		return "", fmt.Errorf("no license found in ENV %s", licenseEnv)
	}
	return license, nil
}

// Get labels for this cluster
func GetLabels(license string) []prompb.Label {
	return []prompb.Label{
		{
			Name:  "__name__",
			Value: "training_operator_active_size",
		},
		{
			Name:  "license",
			Value: license,
		},
	}
}

// Get the current active resource usage from promauto
func GetCurrentGPUUsage() prompb.TimeSeries {
	license, err := getLicense()
	if err != nil {
		return prompb.TimeSeries{}
	}

	activeSize := trainingoperatorcommon.ActiveSizeGaugeGetValue()
	return prompb.TimeSeries{
		Labels: GetLabels(license),
		Samples: []prompb.Sample{
			{
				Value:     float64(activeSize),
				Timestamp: time.Now().UnixNano() / int64(time.Millisecond),
			},
		},
	}
}
