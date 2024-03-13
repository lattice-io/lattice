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

package config

import (
	corev1 "k8s.io/api/core/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// LatticeConfig contains the configuration for the lattice controller.
// It is used by both the autoscaler and the reconciler.
type LatticeConfig struct {
	// The namespace that the lattice operator is managing.
	Namespace string

	// Node selectors to schedule TrainingJob pods.
	JobNodeSelector client.MatchingLabels

	// JFrogSecret is a secret containing the username and password for the JFrog registry.
	JFrogSecret *JFrogSecret

	// Resource Unit that the operator uses to schedule TrainingJobs
	ResourceUnit corev1.ResourceName
	// Debug world size manually specifies the world size to debug the operator
	// If this is not set, the operator will get the world size from the worker nodes.
	DebugWorldSize *int32

	// The following fields are used by lattice-addon and lattice-agent
	LatticeAddonsCheckpointType     string
	LatticeAddonsCheckpointEndpoint string
	LatticeAddonsCheckpointPort     string
	LatticeAgentRendezvousBackend   string
	LatticeAgentRendezvousEndpoint  string
	LatticeAgentRendezvousPort      string
}

// JFrogSecret is a secret containing the username and password for the JFrog registry.
// We configure JFrog authentication for worker pods so that they can pull installers for
// lattice-agent and lattice-addon when injectLattice is set to true.
type JFrogSecret struct {
	Username string
	Password string
}
