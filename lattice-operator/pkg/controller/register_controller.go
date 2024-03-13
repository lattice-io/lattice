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
	"fmt"
	"strings"

	breezemlv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	"github.com/breezeml/lattice-operator/pkg/billing"
	"github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/autoscaler"
	latticeconfig "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/config"
	"github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/reconciler"
	"sigs.k8s.io/controller-runtime/pkg/manager"
)

const (
	ErrTemplateSchemeNotSupported = "scheme %s is not supported yet"

	ReconcilerControllerType = breezemlv1.TrainingJobKind + "Reconciler"
	AutoScalerControllerType = breezemlv1.TrainingJobKind + "AutoScaler"
)

type ControllerSetupFunc func(manager manager.Manager, billingDaemon *billing.Daemon, config *latticeconfig.LatticeConfig) error

var SupportedControllers = map[string]ControllerSetupFunc{
	ReconcilerControllerType: func(mgr manager.Manager, billingDaemon *billing.Daemon, config *latticeconfig.LatticeConfig) error {
		return reconciler.NewReconciler(mgr, billingDaemon, config).SetupWithManager(mgr)
	},
	AutoScalerControllerType: func(mgr manager.Manager, billingDaemon *billing.Daemon, config *latticeconfig.LatticeConfig) error {
		return autoscaler.NewReconciler(mgr, billingDaemon, config).SetupWithManager(mgr)
	},
}

type EnabledControllers []string

func (ec *EnabledControllers) String() string {
	return strings.Join(*ec, ",")
}

func (ec *EnabledControllers) Set(kind string) error {
	kind = strings.ToLower(kind)
	for supportedKind := range SupportedControllers {
		if strings.ToLower(supportedKind) == kind {
			*ec = append(*ec, supportedKind)
			return nil
		}
	}
	return fmt.Errorf(ErrTemplateSchemeNotSupported, kind)
}

func (ec *EnabledControllers) FillAll() {
	for supportedKind := range SupportedControllers {
		*ec = append(*ec, supportedKind)
	}
}

func (ec *EnabledControllers) Empty() bool {
	return len(*ec) == 0
}
