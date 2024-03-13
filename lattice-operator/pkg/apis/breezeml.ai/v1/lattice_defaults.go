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

package v1

import (
	"fmt"

	v1 "github.com/kubeflow/common/pkg/apis/common/v1"
	"github.com/kubeflow/common/pkg/util"
	"github.com/sirupsen/logrus"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/utils/pointer"
)

func addLatticeDefaultingFuncs(scheme *runtime.Scheme) error {
	return RegisterDefaults(scheme)
}

func SetDefaultReplicas(jobSpec *v1.ReplicaSpec, replicas int32) {
	if jobSpec != nil && jobSpec.Replicas == nil {
		jobSpec.Replicas = pointer.Int32(replicas)
	}
}

func setDefaultRestartPolicy(jobSpec *v1.ReplicaSpec, policy v1.RestartPolicy) {
	if jobSpec != nil && jobSpec.RestartPolicy == "" {
		jobSpec.RestartPolicy = policy
	}
}

func setDefaultFramework(jobSpec *TrainingJobSpec) {
	if jobSpec.Framework == nil {
		jobSpec.Framework = new(TrainingJobFramework)
		*jobSpec.Framework = TrainingJobFrameworkPyTorch
	}
}

func setDefaultInjectLattice(jobSpec *TrainingJobSpec) {
	if jobSpec.InjectLattice == nil {
		jobSpec.InjectLattice = new(bool)
		*jobSpec.InjectLattice = false
	}
}

func setDefaultPriority(jobSpec *TrainingJobSpec) {
	if jobSpec.Priority == nil {
		jobSpec.Priority = new(int32)
		*jobSpec.Priority = 0
	}
}

func SetDefaults_TrainingJob(job *TrainingJob) {
	// Set default cleanpod policy to All.
	if job.Spec.RunPolicy.CleanPodPolicy == nil {
		policy := v1.CleanPodPolicyAll
		job.Spec.RunPolicy.CleanPodPolicy = &policy
	}

	SetDefaultReplicas(job.Spec.ReplicaSpecs, 1)
	setDefaultRestartPolicy(job.Spec.ReplicaSpecs, TrainingJobDefaultRestartPolicy)
	setDefaultFramework(&job.Spec)
	setDefaultInjectLattice(&job.Spec)
	setDefaultPriority(&job.Spec)

	// if condition is empty, we add a TrainingJobCreated condition
	if job.Status.ExecStatus.Conditions == nil {
		msg := fmt.Sprintf("TrainingJob %s is created.", job.Name)
		if err := util.UpdateJobConditions(&job.Status.ExecStatus, v1.JobCreated, "TrainingJobCreated", msg); err != nil {
			logrus.Error(err, "append job condition error")
		}
	}
}
