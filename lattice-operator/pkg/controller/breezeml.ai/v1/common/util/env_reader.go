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

package util

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	latticeconfig "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/config"
	corev1 "k8s.io/api/core/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

const (
	// Env names for the lattice operator
	OperatorEnvJobNodeSelectorFile        = "LATTICE_JOB_NODE_SELECTOR_PATH" // The file that configures the job node selector.
	OperatorEnvJFrogSecretPath            = "LATTICE_JFROG_SECRET_PATH"      // The path to the folder that contains the JFrog secret.
	OperatorEnvResourceSchedulingUnit     = "RESOURCE_SCHEDULING_UNIT"       // The unit of resource scheduling, e.g. "node", "nvidia.com/gpu"
	OperatorEnvDebugWorldSize             = "DEBUG_WORLD_SIZE"               // Manually specified world size for debugging
	OperatorEnvLatticeCheckpointType      = "ADDONS_CHECKPOINT_TYPE"         // The type of checkpointing to use, e.g. "remote", by lattice-addon
	OperatorEnvLatticeCkptServiceEndpoint = "CHECKPOINT_SERVICE_ENDPOINT"    // The endpoint of the checkpoint service used by lattice-addon
	OperatorEnvLatticeCkptServicePort     = "CHECKPOINT_SERVICE_PORT"        // The port of the checkpoint service used by lattice-addon
	OperatorEnvLatticeRdzvServiceEndpoint = "RDZV_SERVICE_ENDPOINT"          // The endpoint of the rendezvous service used by lattice-agent
	OperatorEnvLatticeRdzvServicePort     = "RDZV_SERVICE_PORT"              // The port of the rendezvous service used by lattice-agent
	OperatorEnvLatticeRdzvBackend         = "RDZV_BACKEND"                   // The backend of the rendezvous service used by lattice-agent
)

// Get the job node selector from the config map specified by the helm deployment
// It determines which nodes we should dispatch worker pods to.
// It is used:
//   - by the autoscaler to determine resources we have in total
//   - by the reconciler to add node selector information to the job
func GetJobNodeSelector() client.MatchingLabels {
	if fileName, ok := os.LookupEnv(OperatorEnvJobNodeSelectorFile); ok {
		// Read the file
		if file, err := os.Open(fileName); err == nil {
			defer file.Close()
			scanner := bufio.NewScanner(file)
			rawData := make([]string, 0)
			for scanner.Scan() {
				rawData = append(rawData, scanner.Text())
			}
			return parseNodeSelectors(rawData)
		} else {
			fmt.Println("Failed to open job node selector file: ", err)
		}
	}
	return make(client.MatchingLabels)
}

// Get the resource type's name we use to schedule jobs
func GetResourceType() corev1.ResourceName {
	if resourceSchedulingUnit, ok := os.LookupEnv(OperatorEnvResourceSchedulingUnit); ok {
		return corev1.ResourceName(resourceSchedulingUnit)
	} else {
		return corev1.ResourceName(NodeResourceType)
	}
}

// Get the manually specified world size for debugging
func GetDebugWorldSize() (*int32, error) {
	if debugWorldSize, ok := os.LookupEnv(OperatorEnvDebugWorldSize); ok {
		// We manually set up the world size for debugging
		clusterSizeInt, err := strconv.Atoi(debugWorldSize)
		if err != nil {
			return nil, fmt.Errorf("DEBUG_WORLD_SIZE should be a positive integer")
		} else if clusterSizeInt <= 0 {
			return nil, fmt.Errorf("DEBUG_WORLD_SIZE should be a positive integer")
		} else {
			clusterSize := int32(clusterSizeInt)
			return &clusterSize, nil
		}
	} else {
		return nil, fmt.Errorf("DEBUG_WORLD_SIZE is not set")
	}
}

// Get the Jfrog username and password from the Kubernetes secret
func GetJfrogSecret() (*latticeconfig.JFrogSecret, error) {
	jfrogSecretPath := os.Getenv(OperatorEnvJFrogSecretPath)
	if len(jfrogSecretPath) == 0 {
		return nil, fmt.Errorf("environment variable %s not configured", OperatorEnvJFrogSecretPath)
	}

	// Get the Jfrog username and password from the secret file
	usernameFile := filepath.Join(jfrogSecretPath, "username")
	passwordFile := filepath.Join(jfrogSecretPath, "password")

	// Read the username and password
	username, err := os.ReadFile(usernameFile)
	if err != nil {
		return nil, fmt.Errorf("failed to read JFrog secret file: %v", err)
	}
	password, err := os.ReadFile(passwordFile)
	if err != nil {
		return nil, fmt.Errorf("failed to read JFrog secret file: %v", err)
	}

	// Create the JfrogSecret object
	JfrogSecret := latticeconfig.JFrogSecret{
		Username: string(username),
		Password: string(password),
	}

	// remove the newline character from the end of the username and password
	JfrogSecret.Username = strings.TrimSuffix(JfrogSecret.Username, "\n")
	JfrogSecret.Password = strings.TrimSuffix(JfrogSecret.Password, "\n")

	return &JfrogSecret, nil
}

// Get the checkpoint type for lattice-addon
func GetLatticeAddonsCheckpointType() string {
	return os.Getenv(OperatorEnvLatticeCheckpointType)
}

// Get the checkpoint service endpoint for lattice-addon
func GetLatticeAddonsCheckpointEndpoint() string {
	return os.Getenv(OperatorEnvLatticeCkptServiceEndpoint)
}

// Get the checkpoint service port for lattice-addon
func GetLatticeAddonsCheckpointPort() string {
	return os.Getenv(OperatorEnvLatticeCkptServicePort)
}

// Get the rendezvous service endpoint for lattice-agent
func GetLatticeAgentRendezvousEndpoint() string {
	return os.Getenv(OperatorEnvLatticeRdzvServiceEndpoint)
}

// Get the rendezvous service port for lattice-agent
func GetLatticeAgentRendezvousPort() string {
	return os.Getenv(OperatorEnvLatticeRdzvServicePort)
}

// Get the rendezvous backend for lattice-agent
func GetLatticeAgentRendezvousBackend() string {
	return os.Getenv(OperatorEnvLatticeRdzvBackend)
}
