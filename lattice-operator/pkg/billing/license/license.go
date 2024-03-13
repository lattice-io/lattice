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

package license

import (
	"fmt"
	"os"
)

const (
	licenseEnv = "LATTICE_LICENSE"
)

// Abstract License interface
// License providers should implement ValidateLicense()
type LicenseInterface interface {
	ValidateLicense() bool
}

// Abstract License
type License struct {
	LicenseInterface
}

// Helper function to get the license from the environment
func GetLicense() (string, error) {
	license, ok := os.LookupEnv(licenseEnv)
	if !ok {
		return "", fmt.Errorf("no license found in ENV %s", licenseEnv)
	}
	return license, nil
}
