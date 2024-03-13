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

package types

import (
	"time"

	"lattice-api-server/pkg/prometheus"

	commonv1 "github.com/kubeflow/common/pkg/apis/common/v1"

	//v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

const (
	TrainingJobKind = "TrainingJob"

	TrainingJobSingular = "trainingjob"

	TrainingJobPlural = "trainingjobs"

	TrainingJobDefaultContainerName = "trainingjob"

	TrainingJobDefaultContainerPortName = "trainingjob-port"

	// TODO: currently it is hard-written to pytorch. It should be configurable with the api later.
	TrainingJobFrameworkName = "pytorch"

	// TrainingJobDefaultRestartPolicy is default RestartPolicy for LatticeReplicaSpec.
	TrainingJobDefaultRestartPolicy = commonv1.RestartPolicyNever

	// Now all replicas should be of type "Worker" since lattice-agent is handling replica type automatically
	TrainingJobDefaultReplicaType = "Worker"

	// The time duration to schedule re-run of the reconcilation
	LatticeDefaultRerunDuration = time.Second * 30

	// The time duration we wait for the scheduler before we remove the pending job from the running list
	LatticeDefaultScheduleFailureDuration = time.Minute * 5

	// The base cooldown time for schedule failure jobs
	// If a job failed to be scheduled, we only attempt to requeue the job after a certain time
	// TODO: this is kind of an ad-hoc fix. We need some better ways to communicate with the scheduler.
	//       However, right now let's keep things simple. Schedule failure is out of our scope.
	//       We don't need to get a perfect solution.
	LatticeDefaultCooldownDuration = time.Hour * 3
)

type TrainingJobFramework string

const (
	// in the current version, users will need to specify
	// what framework they are using
	// if unset, we use "pytorch"
	// the framework will be sent to the agent as an environment variable
	TrainingJobFrameworkGeneric TrainingJobFramework = "generic"
	TrainingJobFrameworkPyTorch TrainingJobFramework = "pytorch"
)

type TrainingJobStage string

const (
	// We assume failures are considered as finished so no restarting
	// When a job is found with no TrainingJobStage defined, it is a new job.
	// The TrainingJob operator is the only thing that will write such status

	// The trainingjob hasn't seen by the reconciler
	TrainingJobStageInit TrainingJobStage = ""
	// The trainingjob is in the waiting list
	TrainingJobStageWaiting TrainingJobStage = "Waiting"
	// The trainingjob is in the running list
	TrainingJobStageRunning TrainingJobStage = "Running"
	// The trainingjob is cancelled by the user (TODO: implement api to receive update from users)
	TrainingJobStageCancelled TrainingJobStage = "Cancelled"
	// The trainingjob has been completed
	TrainingJobStageCompleted TrainingJobStage = "Completed"
	// The trainingjob currently under requeuing cooldown
	TrainingJobStageRequeuing TrainingJobStage = "RequeueCooldown"
)

// +genclient
// +k8s:deepcopy-gen=true
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
//+kubebuilder:subresource:status
//+kubebuilder:printcolumn:name="State",type=string,JSONPath=`.status.stage`
//+kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`
// +kubebuilder:subresource:scale:specpath=.spec.ReplicaSpecs.Worker.replicas,statuspath=.status.replicaStatuses.Active,selectorpath=.status.labelSelector

// TrainingJob is the Schema for the trainingjobs API
type TrainingJob struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   TrainingJobSpec   `json:"spec,omitempty"`
	Status TrainingJobStatus `json:"status,omitempty"`
}

// +k8s:deepcopy-gen=true

// TrainingJobSpec defines the desired state of TrainingJob
type TrainingJobSpec struct {
	// RunPolicy encapsulates various runtime policies of the distributed training
	// job, for example how to clean up resources and how long the job can stay
	// active.
	RunPolicy commonv1.RunPolicy `json:"runPolicy"`

	// ReplicaSpec (value). Specifies configuration for containers.
	// It no longer handles the number of nodes
	// The lattice operator will generate replica numbers dynamically
	ReplicaSpecs *commonv1.ReplicaSpec `json:"replicaSpecs"`

	// The following two parameters configure elastic behavior of the job.
	// We only consider running the job with [MinSize, MaxSize] nodes.
	// If unspecified, they are set to [1,1]
	MinSize *int32 `json:"minSize,omitempty"`
	MaxSize *int32 `json:"maxSize,omitempty"`

	// We use this part of the spec as a way to determine whether we should
	// inject the Lattice Agent and Lattice Addons using the
	// Lattice Installer. Currently, enabling this imposes the requirement
	// that the container used must have python and pip installed and
	// MUST have an explicit command in the yaml file, not use the implicit
	// command in the docker
	// If unspecified, set to false
	// +optional
	InjectLattice *bool `json:"injectLattice"`

	// The framework of the TrainingJob
	// Will be sent to agent as an ENV variable
	// Default: pytorch
	// +optional
	Framework *TrainingJobFramework `json:"framework,omitempty"`

	// Priority of the job as integers
	// A job with higher priority will always be scheduled first
	// A job with higher priority can take over resources from lower ones preemptively
	// Default: 0
	// +optional
	Priority *int32 `json:"priority,omitempty"`
}

// +k8s:deepcopy-gen=true
// +k8s:openapi-gen=true
// TrainingJobStatus defines the observed state of TrainingJob
type TrainingJobStatus struct {
	// INSERT ADDITIONAL STATUS FIELD - define observed state of cluster
	// Important: Run "make" to regenerate code after modifying this file

	// Note: execution status handles single-job scheduling information after
	//       the autoscaling algorithm has determined intended replicaSpecs for it.
	//       the reconciler will try to control the exec status to match the
	//       indended status determined by the autoscaler
	ExecStatus commonv1.JobStatus `json:"execStatus"`

	// For autoscaling:
	//   CurrentSize: whether the job has been scheduled
	//   Stage: whether the job is waiting, running, or has finished
	// These are the *intended* status of the jobs. At runtime, we reconcile jobs to meet such status.
	CurrentSize int32            `json:"currentSize,omitempty"`
	Stage       TrainingJobStage `json:"stage,omitempty"`

	// For autoscaling:
	//   SubmitTime: the time when the job was submitted to the cluster.
	//     Note - it is different from the StartTime in LagacyStatus. Submitted jobs might not be started.
	// It is represented in RFC3339 form and is in UTC.
	SubmitTime *metav1.Time `json:"submitTime,omitempty"`

	// For autoscaling:
	//   QueuedTime: the time when the job was put into the waiting list/running list
	//   By default it is the same as SubmitTime. However, if the job failed to be scheduled to specific nodes,
	//   the value will be reset. We use this timestamp to allow FIFO.
	QueuedTime *metav1.Time `json:"queuedTime,omitempty"`

	// Time when the job was last executed
	LastExecTime *metav1.Time `json:"lastExecTime,omitempty"`

	// Time when the job was completed
	CompletionTime *metav1.Time `json:"completionTime,omitempty"`

	// Time when we want to remove the job from the running list if some pod is still pending
	// Every time the autoscaler touches currentSize or Stage, we need to reset it to nil.
	// We set this when we see some pod are seen pending for the first time.
	// Nil by default
	RequeueTime *metav1.Time `json:"requeueTime,omitempty"`

	// Time before which the trainingjob is on cooldown
	// It is used when we decide to remove the schedule-failure job from the running list
	// We only attempt to requeue the job once we pass the cooldown time
	// Nil by default
	CooldownTime *metav1.Time `json:"cooldownTime,omitempty"`
}

// +k8s:deepcopy-gen=true
// +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object

// TrainingJobList contains a list of TrainingJob
type TrainingJobList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []TrainingJob `json:"items"`
}

// Job the Job class for kubernetes cluster.
type Job struct {
	ID          string                       `json:"key"`
	Namespace   string                       `json:"namespace"`
	Name        string                       `json:"name"`
	Experiment  string                       `json:"experiment"`
	User        string                       `json:"user"`
	Status      string                       `json:"status"`
	StartTime   string                       `json:"start_time"`
	RunningTime string                       `json:"running_time"`
	CurrentSize int32                        `json:"job_size"`
	RunningSize int32                        `json:"running_size"`
	Priority    int32                        `json:"priority"`
	CPUs        int64                        `json:"cpus"`
	GPUs        int64                        `json:"gpus"`
	Memory      float64                      `json:"memory"`
	DownloadURL string                       `json:"download_url"`
	SizeHistory []prometheus.PrometheusValue `json:"size_history"`
}

// ClusterResizePatch: api to update the size of the worker nodegroup
type ClusterResizePatch struct {
	DesiredSize int64 `json:"desired_size"`
}

// JobPriorityPatch: api template for job priority update patch
// It contains only partial information from the TrainingJob api to
// make sure users cannot modify other fields of the TrainingJob.
type JobPriorityPatch struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec JobSpecPriorityPatch `json:"spec,omitempty"`
}

// JobSpecPriorityPatch: partial TrainingJobSpec with the purpose
// to update only job priority.
type JobSpecPriorityPatch struct {
	// Priority of the job as integers
	// A job with higher priority will always be scheduled first
	// A job with higher priority can take over resources from lower ones preemptively
	// Default: 0
	// +optional
	Priority *int32 `json:"priority,omitempty"`
}

// Wrapper for Example trainingjobs (i.e., Resnet and Bert)
// We only leave the number of epochs configurable.
type TrainingJobExampleWrapper struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	// +optional
	Epochs *int64 `json:"epochs,omitempty"`
}

// JobPlace maps node names to a list of jobs running on the node
type JobPlacement map[string][]string

// GetJobResponse is the response for the GetJob API
type GetJobResponse struct {
	Placement JobPlacement `json:"placement"`
	Jobs      []Job        `json:"jobs"`
}

type Dataset struct {
	Name string `json:"name"`
	Location string `json:"location"`
}

// DeepCopyInto is an autogenerated deepcopy function, copying the receiver, writing into out. in must be non-nil.
func (in *TrainingJobSpec) DeepCopyInto(out *TrainingJobSpec) {
	*out = *in
	in.RunPolicy.DeepCopyInto(&out.RunPolicy)
	if in.ReplicaSpecs != nil {
		in, out := &in.ReplicaSpecs, &out.ReplicaSpecs
		*out = new(commonv1.ReplicaSpec)
		(*in).DeepCopyInto(*out)
	}
	if in.MinSize != nil {
		in, out := &in.MinSize, &out.MinSize
		*out = new(int32)
		**out = **in
	}
	if in.MaxSize != nil {
		in, out := &in.MaxSize, &out.MaxSize
		*out = new(int32)
		**out = **in
	}
	if in.InjectLattice != nil {
		in, out := &in.InjectLattice, &out.InjectLattice
		*out = new(bool)
		**out = **in
	}
	if in.Framework != nil {
		in, out := &in.Framework, &out.Framework
		*out = new(TrainingJobFramework)
		**out = **in
	}
	if in.Priority != nil {
		in, out := &in.Priority, &out.Priority
		*out = new(int32)
		**out = **in
	}
}

// DeepCopy is an autogenerated deepcopy function, copying the receiver, creating a new TrainingJobSpec.
func (in *TrainingJobSpec) DeepCopy() *TrainingJobSpec {
	if in == nil {
		return nil
	}
	out := new(TrainingJobSpec)
	in.DeepCopyInto(out)
	return out
}

// Helper function that gets the mapping between job name and job uid
func (t *TrainingJobList) GetJobNameToUidMap() map[string]string {
	jobNameToUidMap := make(map[string]string)
	for _, job := range t.Items {
		jobNameToUidMap[job.Name] = string(job.UID)
	}
	return jobNameToUidMap
}
