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

package billing

import (
	"time"

	"github.com/breezeml/lattice-operator/pkg/billing/license"
	"github.com/breezeml/lattice-operator/pkg/billing/usage"
	"github.com/prometheus/prometheus/prompb"
)

const (
	DefaultLicenseCheckInterval = 60
	DefaultUsageMonitorInterval = 60
)

type Daemon struct {
	// The operator is allowed to proceed if approved is true.
	approved bool

	// The license provider that validates the license.
	license license.LicenseInterface
	// The interval at which the license should be checked.
	licenseCheckInterval int
	// The ticker that checks the license.
	licenseCheckTicker *time.Ticker

	// The usage monitor interface
	monitor usage.MonitorInterface
	// The interval at which the usage should be pushed.
	usagePushInterval int
	// The ticker that pushes the usage.
	usagePushTicker *time.Ticker
}

func (d *Daemon) IsApproved() bool {
	return d.approved
}

// The license check function that is run on a ticker.
func (d *Daemon) licenseCheck() {
	d.approved = d.license.ValidateLicense()
}

// Start the license check ticker.
func (d *Daemon) Start() {
	// Start the periodic license check
	d.licenseCheckTicker = time.NewTicker(time.Duration(d.licenseCheckInterval) * time.Second)
	go func() {
		for range d.licenseCheckTicker.C {
			d.licenseCheck()
		}
	}()

	// Start the periodic usage push
	d.usagePushTicker = time.NewTicker(time.Duration(d.usagePushInterval) * time.Second)
	go func() {
		for range d.usagePushTicker.C {
			_ = d.monitor.PushMetric([]prompb.TimeSeries{usage.GetCurrentGPUUsage()})
		}
	}()
}
