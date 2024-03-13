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

package reconciler

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"

	"github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/common/util"
	commonv1 "github.com/kubeflow/common/pkg/apis/common/v1"
	"github.com/kubeflow/common/pkg/controller.v1/common"
	"github.com/kubeflow/common/pkg/controller.v1/expectation"
	"github.com/kubeflow/common/pkg/core"
	commonutil "github.com/kubeflow/common/pkg/util"
	utillabels "github.com/kubeflow/common/pkg/util/labels"
	trainutil "github.com/kubeflow/common/pkg/util/train"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/meta"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// This file is inherited from Kubeflow common.
// We reimplement some pod handling functions to customize pod selection during downscaling.
// Pod related metrics no longer work.
// We use custom pod metrics instead.

const (
	// podTemplateRestartPolicyReason is the warning reason when the restart
	// policy is set in pod template.
	podTemplateRestartPolicyReason = "SettedPodTemplateRestartPolicy"
	// exitedWithCodeReason is the normal reason when the pod is exited because of the exit code.
	exitedWithCodeReason = "ExitedWithCode"
	// podTemplateSchedulerNameReason is the warning reason when other scheduler name is set
	// in pod templates with gang-scheduling enabled
	podTemplateSchedulerNameReason = "SettedPodTemplateSchedulerName"
)

// The Name Pool for the pods
// Used to avoid confliction when creating pods
type PodNamePool map[string]struct{}

// Check if the name is in the pool
func (p *PodNamePool) Has(name string) bool {
	_, ok := (*p)[name]
	return ok
}

// Add the name to the pool
func (p *PodNamePool) Add(name string) {
	(*p)[name] = struct{}{}
}

func (r *TrainingJobReconciler) GetPodsForJob(obj interface{}) ([]*corev1.Pod, error) {
	job, err := meta.Accessor(obj)
	if err != nil {
		return nil, err
	}

	// List all pods to include those that don't match the selector anymore
	// but have a ControllerRef pointing to this controller.
	podlist := &corev1.PodList{}
	err = r.List(context.Background(), podlist, client.MatchingLabels(r.GenLabels(job.GetName())), client.InNamespace(job.GetNamespace()))
	if err != nil {
		return nil, err
	}

	return util.ConvertPodList(podlist.Items), nil
}

func (r *TrainingJobReconciler) GetServicesForJob(obj interface{}) ([]*corev1.Service, error) {
	job, err := meta.Accessor(obj)
	if err != nil {
		return nil, err
	}

	// List all pods to include those that don't match the selector anymore
	// but have a ControllerRef pointing to this controller.
	serviceList := &corev1.ServiceList{}
	err = r.List(context.Background(), serviceList, client.MatchingLabels(r.GenLabels(job.GetName())), client.InNamespace(job.GetNamespace()))
	if err != nil {
		return nil, err
	}

	ret := util.ConvertServiceList(serviceList.Items)
	return ret, nil
}

func (r *TrainingJobReconciler) IsMasterRole(replicas map[commonv1.ReplicaType]*commonv1.ReplicaSpec,
	rtype commonv1.ReplicaType, index int) bool {
	return false
}

// Update the replica index of the pod
// It updates both the local pod object, and the pod in the apiserver
func (r *TrainingJobReconciler) UpdatePodReplicaIndex(pod *corev1.Pod, index int) error {
	labels := pod.GetLabels()

	// if the index is the same, do nothing
	currentIndex, err := utillabels.ReplicaIndex(labels)
	if err != nil {
		return err
	}
	if currentIndex == index {
		return nil
	}

	utillabels.SetReplicaIndex(labels, index)
	pod.SetLabels(labels)

	// Patch the pod using
	patch := fmt.Sprintf(`{"metadata":{"labels":{"%s":"%d"}}}`, commonv1.ReplicaIndexLabel, index)

	if err != nil {
		return err
	}

	// Update the job's replica index
	return r.JobController.PodControl.PatchPod(pod.Namespace, pod.Name, []byte(patch))
}

// Put pending pods the tail by resetting their replica index
func (r *TrainingJobReconciler) RelabelPendingPods(pods []*corev1.Pod) error {
	index := 0

	// make a copy of the pods, and sort the pods by replica index
	podsCopy := make([]*corev1.Pod, len(pods))
	copy(podsCopy, pods)
	sort.Slice(podsCopy, func(i, j int) bool {
		iIndex, _ := utillabels.ReplicaIndex(podsCopy[i].GetLabels())
		jIndex, _ := utillabels.ReplicaIndex(podsCopy[j].GetLabels())
		return iIndex < jIndex
	})

	pendingPods := []*corev1.Pod{}

	// First, put all non-pending pods to the head
	for _, pod := range podsCopy {
		if pod.Status.Phase != corev1.PodPending {
			if err := r.UpdatePodReplicaIndex(pod, index); err != nil {
				return err
			}
			index++
		} else {
			pendingPods = append(pendingPods, pod)
		}
	}

	// Then, put all pending pods to the tail
	for _, pod := range pendingPods {
		if err := r.UpdatePodReplicaIndex(pod, index); err != nil {
			return err
		}
		index++
	}

	return nil
}

// ReconcilePods checks and updates pods for each given ReplicaSpec.
// It will requeue the job in case of an error while creating/deleting pods.
func (r *TrainingJobReconciler) ReconcilePods(
	job interface{},
	jobStatus *commonv1.JobStatus,
	pods []*corev1.Pod,
	rType commonv1.ReplicaType,
	spec *commonv1.ReplicaSpec,
	replicas map[commonv1.ReplicaType]*commonv1.ReplicaSpec) error {

	rt := strings.ToLower(string(rType))
	metaObject, ok := job.(metav1.Object)
	if !ok {
		return fmt.Errorf("job is not a metav1.Object type")
	}
	runtimeObject, ok := job.(runtime.Object)
	if !ok {
		return fmt.Errorf("job is not a runtime.Object type")
	}
	jobKey, err := common.KeyFunc(metaObject)
	if err != nil {
		utilruntime.HandleError(fmt.Errorf("couldn't get key for job object %#v: %v", job, err))
		return err
	}
	expectationPodsKey := expectation.GenExpectationPodsKey(jobKey, rt)

	// Convert ReplicaType to lower string.
	logger := commonutil.LoggerForReplica(metaObject, rt)
	// Get all pods for the type rt.
	pods, err = r.FilterPodsForReplicaType(pods, rt)
	if err != nil {
		return err
	}
	numReplicas := int(*spec.Replicas)
	var masterRole bool

	core.InitializeReplicaStatuses(jobStatus, rType)

	// If we have more pods than numReplicas, we need to delete excess pods.
	// We make sure pending pods are deleted first. This is to prevent the following bug in kubeflow/ReplicaSet:
	// 1. ReplicaSet has 2 pods: pod1 is pending, pod2 is running.
	// 2. User scales down replicas to 1.
	// 3. ReplicaSet deletes pod2. However, there is a bug that pod2 returns exit code 0 in this scenario.
	// 4. ReplicaSet then will treat it as successful, and mark itself as complete.
	// 5. The TrainingJob will be marked as successful.
	if len(pods) > numReplicas {
		if err := r.RelabelPendingPods(pods); err != nil {
			return err
		}
	}

	podNamePool := generatePodNamePool(pods)

	// GetPodSlices will return enough information here to make decision to add/remove/update resources.
	//
	// For example, let's assume we have pods with replica-index 0, 1, 2
	// If replica is 4, return a slice with size 4. [[0],[1],[2],[]], a pod with replica-index 3 will be created.
	//
	// If replica is 1, return a slice with size 3. [[0],[1],[2]], pod with replica-index 1 and 2 are out of range and will be deleted.
	podSlices := r.GetPodSlices(pods, numReplicas, logger)
	for index, podSlice := range podSlices {
		if len(podSlice) > 1 {
			logger.Warningf("We have too many pods for %s %d", rt, index)
		} else if len(podSlice) == 0 {
			logger.Infof("Need to create new pod: %s-%d", rt, index)

			// check if this replica is the master role
			masterRole = r.Controller.IsMasterRole(replicas, rType, index)
			err = r.createNewPod(job, rt, index, spec, masterRole, replicas, podNamePool)
			if err != nil {
				return err
			}
		} else {
			// Check the status of the current pod.
			pod := podSlice[0]

			// check if the index is in the valid range, if not, we should kill the pod
			if index < 0 || index >= numReplicas {
				err = r.PodControl.DeletePod(pod.Namespace, pod.Name, runtimeObject)
				if err != nil {
					return err
				}
				// Deletion is expected
				r.Expectations.RaiseExpectations(expectationPodsKey, 0, 1)
			}

			// Get the exit code of the container.
			var exitCode int32 = 0xbeef // magic number
			for _, status := range pod.Status.ContainerStatuses {
				state := status.State
				if status.Name == r.Controller.GetDefaultContainerName() && state.Terminated != nil {
					exitCode = state.Terminated.ExitCode
					logger.Infof("Pod: %v.%v exited with code %v", pod.Namespace, pod.Name, exitCode)
					r.Recorder.Eventf(runtimeObject, corev1.EventTypeNormal, exitedWithCodeReason, "Pod: %v.%v exited with code %v", pod.Namespace, pod.Name, exitCode)
				}
			}
			// Check if the pod is retryable.
			if pod.Status.Phase == corev1.PodFailed &&
				(spec.RestartPolicy == commonv1.RestartPolicyExitCode && trainutil.IsRetryableExitCode(exitCode) ||
					spec.RestartPolicy == commonv1.RestartPolicyOnFailure ||
					spec.RestartPolicy == commonv1.RestartPolicyAlways) {
				logger.Infof("Need to restart the pod: %v.%v", pod.Namespace, pod.Name)
				if err := r.PodControl.DeletePod(pod.Namespace, pod.Name, runtimeObject); err != nil {
					return err
				}
				// Deletion is expected
				r.Expectations.RaiseExpectations(expectationPodsKey, 0, 1)

			}

			core.UpdateJobReplicaStatuses(jobStatus, rType, pod)
		}
	}
	return nil
}

// generatePodNamePool generates a map of pod names.
func generatePodNamePool(pods []*corev1.Pod) *PodNamePool {
	podNamePool := make(PodNamePool)
	for _, pod := range pods {
		podNamePool[pod.Name] = struct{}{}
	}
	return &podNamePool
}

// generateUniquePodName generates a unique pod name given PodNamePool.
func generateUniquePodName(jobName string, rt string, podNamePool *PodNamePool) string {
	nameIdx := 0
	// Increase nameIdx until we find a name that is not in the podNamePool.
	for {
		podName := common.GenGeneralName(jobName, rt, strconv.Itoa(nameIdx))
		if podNamePool.Has(podName) {
			nameIdx++
		} else {
			return podName
		}
	}
}

// createNewPod creates a new pod for the given index and type.
func (r *TrainingJobReconciler) createNewPod(job interface{}, rt string, index int, spec *commonv1.ReplicaSpec, masterRole bool,
	replicas map[commonv1.ReplicaType]*commonv1.ReplicaSpec, podNamePool *PodNamePool) error {

	metaObject, ok := job.(metav1.Object)
	if !ok {
		return fmt.Errorf("job is not a metav1.Object type")
	}
	runtimeObject, ok := job.(runtime.Object)
	if !ok {
		return fmt.Errorf("job is not a runtime.Object type")
	}
	jobKey, err := common.KeyFunc(metaObject)
	if err != nil {
		utilruntime.HandleError(fmt.Errorf("couldn't get key for job object %#v: %v", job, err))
		return err
	}
	logger := commonutil.LoggerForReplica(metaObject, rt)

	// Set type and index for the worker.
	labels := r.GenLabels(metaObject.GetName())
	utillabels.SetReplicaType(labels, rt)
	utillabels.SetReplicaIndex(labels, index)

	if masterRole {
		utillabels.SetJobRole(labels, "master")
	}

	podTemplate := spec.Template.DeepCopy()

	podTemplate.Name = generateUniquePodName(metaObject.GetName(), rt, podNamePool)
	podNamePool.Add(podTemplate.Name)

	if podTemplate.Labels == nil {
		podTemplate.Labels = make(map[string]string)
	}

	for key, value := range labels {
		podTemplate.Labels[key] = value
	}

	idxStr := strconv.Itoa(index)
	if err := r.Controller.SetClusterSpec(job, podTemplate, rt, idxStr); err != nil {
		return err
	}

	// Submit a warning event if the user specifies restart policy for
	// the pod template. We recommend to set it from the replica level.
	if podTemplate.Spec.RestartPolicy != corev1.RestartPolicy("") {
		errMsg := "Restart policy in pod template will be overwritten by restart policy in replica spec"
		logger.Warning(errMsg)
		r.Recorder.Event(runtimeObject, corev1.EventTypeWarning, podTemplateRestartPolicyReason, errMsg)
	}
	core.SetRestartPolicy(podTemplate, spec)

	// if gang-scheduling is enabled:
	// 1. if user has specified other scheduler, we report a warning without overriding any fields.
	// 2. if no SchedulerName is set for pods, then we set the SchedulerName to "volcano".
	if r.Config.EnableGangScheduling() {
		if isCustomSchedulerSet(replicas, r.PodGroupControl.GetSchedulerName()) {
			errMsg := "Another scheduler is specified when gang-scheduling is enabled and it will not be overwritten"
			logger.Warning(errMsg)
			r.Recorder.Event(runtimeObject, corev1.EventTypeWarning, podTemplateSchedulerNameReason, errMsg)
		}
		r.PodGroupControl.DecoratePodTemplateSpec(podTemplate, metaObject, rt)
	}

	// Creation is expected when there is no error returned
	// We use `RaiseExpectations` here to accumulate expectations since `SetExpectations` has no such kind of ability
	expectationPodsKey := expectation.GenExpectationPodsKey(jobKey, rt)
	r.Expectations.RaiseExpectations(expectationPodsKey, 1, 0)

	controllerRef := r.GenOwnerReference(metaObject)
	err = r.PodControl.CreatePodsWithControllerRef(metaObject.GetNamespace(), podTemplate, runtimeObject, controllerRef)
	if err != nil && errors.IsTimeout(err) {
		// Pod is created but its initialization has timed out.
		// If the initialization is successful eventually, the
		// controller will observe the creation via the informer.
		// If the initialization fails, or if the pod keeps
		// uninitialized for a long time, the informer will not
		// receive any update, and the controller will create a new
		// pod when the expectation expires.
		return nil
	} else if err != nil {
		// Since error occurred(the informer won't observe this pod),
		// we decrement the expected number of creates
		// and wait until next reconciliation
		r.Expectations.CreationObserved(expectationPodsKey)
		return err
	}
	return nil
}

func isCustomSchedulerSet(replicas map[commonv1.ReplicaType]*commonv1.ReplicaSpec, gangSchedulerName string) bool {
	for _, spec := range replicas {
		if spec.Template.Spec.SchedulerName != "" && spec.Template.Spec.SchedulerName != gangSchedulerName {
			return true
		}
	}
	return false
}
