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

package controller_v1

import (
	"testing"
)

func TestEnabledControllers(t *testing.T) {
	testES := EnabledControllers{}

	if testES.String() != "" {
		t.Errorf("empty EnabledControllers converted no-empty string %s", testES.String())
	}

	if !testES.Empty() {
		t.Error("Empty method returned false for empty EnabledControllers")
	}

	if testES.Set(ReconcilerControllerType) != nil {
		t.Error("failed to restore reconciler(trainingjob)")
	} else {
		stored := false
		for _, kind := range testES {
			if kind == ReconcilerControllerType {
				stored = true
			}
		}
		if !stored {
			t.Errorf("%s not successfully registered", ReconcilerControllerType)
		}
	}

	if testES.Set(AutoScalerControllerType) != nil {
		t.Error("failed to restore autoscaler(trainingjob)")
	} else {
		stored := false
		for _, kind := range testES {
			if kind == AutoScalerControllerType {
				stored = true
			}
		}
		if !stored {
			t.Errorf("%s not successfully registered", AutoScalerControllerType)
		}
	}

	dummyJob := "dummyjob"
	if testES.Set(dummyJob) == nil {
		t.Errorf("successfully registerd non-supported job %s", dummyJob)
	}

	if testES.Empty() {
		t.Error("Empty method returned true for non-empty EnabledControllers")
	}

	es2 := EnabledControllers{}
	es2.FillAll()
	if es2.Empty() {
		t.Error("Empty method returned true for fully registered EnabledControllers")
	}
}
