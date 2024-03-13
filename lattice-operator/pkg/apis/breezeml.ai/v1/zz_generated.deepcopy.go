//go:build !ignore_autogenerated
// +build !ignore_autogenerated

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

// Code generated by deepcopy-gen. DO NOT EDIT.

package v1

import (
	commonv1 "github.com/kubeflow/common/pkg/apis/common/v1"
	runtime "k8s.io/apimachinery/pkg/runtime"
)

// DeepCopyInto is an autogenerated deepcopy function, copying the receiver, writing into out. in must be non-nil.
func (in *TrainingJob) DeepCopyInto(out *TrainingJob) {
	*out = *in
	out.TypeMeta = in.TypeMeta
	in.ObjectMeta.DeepCopyInto(&out.ObjectMeta)
	in.Spec.DeepCopyInto(&out.Spec)
	in.Status.DeepCopyInto(&out.Status)
	return
}

// DeepCopy is an autogenerated deepcopy function, copying the receiver, creating a new TrainingJob.
func (in *TrainingJob) DeepCopy() *TrainingJob {
	if in == nil {
		return nil
	}
	out := new(TrainingJob)
	in.DeepCopyInto(out)
	return out
}

// DeepCopyObject is an autogenerated deepcopy function, copying the receiver, creating a new runtime.Object.
func (in *TrainingJob) DeepCopyObject() runtime.Object {
	if c := in.DeepCopy(); c != nil {
		return c
	}
	return nil
}

// DeepCopyInto is an autogenerated deepcopy function, copying the receiver, writing into out. in must be non-nil.
func (in *TrainingJobList) DeepCopyInto(out *TrainingJobList) {
	*out = *in
	out.TypeMeta = in.TypeMeta
	in.ListMeta.DeepCopyInto(&out.ListMeta)
	if in.Items != nil {
		in, out := &in.Items, &out.Items
		*out = make([]TrainingJob, len(*in))
		for i := range *in {
			(*in)[i].DeepCopyInto(&(*out)[i])
		}
	}
	return
}

// DeepCopy is an autogenerated deepcopy function, copying the receiver, creating a new TrainingJobList.
func (in *TrainingJobList) DeepCopy() *TrainingJobList {
	if in == nil {
		return nil
	}
	out := new(TrainingJobList)
	in.DeepCopyInto(out)
	return out
}

// DeepCopyObject is an autogenerated deepcopy function, copying the receiver, creating a new runtime.Object.
func (in *TrainingJobList) DeepCopyObject() runtime.Object {
	if c := in.DeepCopy(); c != nil {
		return c
	}
	return nil
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
	return
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

// DeepCopyInto is an autogenerated deepcopy function, copying the receiver, writing into out. in must be non-nil.
func (in *TrainingJobStatus) DeepCopyInto(out *TrainingJobStatus) {
	*out = *in
	in.ExecStatus.DeepCopyInto(&out.ExecStatus)
	if in.SubmitTime != nil {
		in, out := &in.SubmitTime, &out.SubmitTime
		*out = (*in).DeepCopy()
	}
	if in.QueuedTime != nil {
		in, out := &in.QueuedTime, &out.QueuedTime
		*out = (*in).DeepCopy()
	}
	if in.LastExecTime != nil {
		in, out := &in.LastExecTime, &out.LastExecTime
		*out = (*in).DeepCopy()
	}
	if in.CompletionTime != nil {
		in, out := &in.CompletionTime, &out.CompletionTime
		*out = (*in).DeepCopy()
	}
	if in.RequeueTime != nil {
		in, out := &in.RequeueTime, &out.RequeueTime
		*out = (*in).DeepCopy()
	}
	if in.CooldownTime != nil {
		in, out := &in.CooldownTime, &out.CooldownTime
		*out = (*in).DeepCopy()
	}
	return
}

// DeepCopy is an autogenerated deepcopy function, copying the receiver, creating a new TrainingJobStatus.
func (in *TrainingJobStatus) DeepCopy() *TrainingJobStatus {
	if in == nil {
		return nil
	}
	out := new(TrainingJobStatus)
	in.DeepCopyInto(out)
	return out
}
