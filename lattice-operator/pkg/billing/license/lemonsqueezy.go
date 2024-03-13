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
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

const (
	LicenseServerEndpoint = "https://api.lemonsqueezy.com/v1/licenses/validate"
)

// These variables are set at built-time.
var (
	LemonSqueezyStoreID     int
	LemonSqueezyProductID   int
	LemonSqueezyProductName string
)

type LicenseKey struct {
	ID     int    `json:"id"`
	Status string `json:"status"`
	Key    string `json:"key"`
}

type LicenseMeta struct {
	StoreID     int    `json:"store_id"`
	ProductID   int    `json:"product_id"`
	ProductName string `json:"product_name"`
}

type LicenseResponse struct {
	Valid      bool        `json:"valid"`
	LicenseKey LicenseKey  `json:"license_key"`
	Meta       LicenseMeta `json:"meta"`
}

type LemonSqueezyLicense struct {
	License
	StoreID     int
	ProductID   int
	ProductName string
	LicenseKey  string
}

// Generate a new LemonSqueezyLicense with default metadata
func NewLemonSqueezyLicense() *LemonSqueezyLicense {
	license, _ := GetLicense()

	return &LemonSqueezyLicense{
		StoreID:     LemonSqueezyStoreID,
		ProductID:   LemonSqueezyProductID,
		ProductName: LemonSqueezyProductName,
		LicenseKey:  license,
	}
}

// ValidateLicense checks that the license is valid and the metadata is correct.
func (l *LemonSqueezyLicense) ValidateLicense() bool {
	// Send a POST request to LicenseServerEndpoint
	// with the license as a JSON body.
	// If the response is 200 OK and metadata is correct, return true.
	// Otherwise, we return false.
	jsonBody := fmt.Sprintf(`{"license_key": "%s"}`, l.LicenseKey)

	resp, err := http.Post(LicenseServerEndpoint, "application/json", strings.NewReader(jsonBody))
	if err != nil || resp.StatusCode != http.StatusOK {
		return false
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return false
	}

	// Unmarshal the response body into a LicenseResponse struct.
	var licenseResponse LicenseResponse
	err = json.Unmarshal(body, &licenseResponse)
	if err != nil {
		return false
	}

	// Check that the license is valid and the metadata is correct.
	if !licenseResponse.Valid ||
		licenseResponse.Meta.StoreID != l.StoreID ||
		licenseResponse.Meta.ProductID != l.ProductID ||
		licenseResponse.Meta.ProductName != l.ProductName {
		return false
	}

	return true
}
