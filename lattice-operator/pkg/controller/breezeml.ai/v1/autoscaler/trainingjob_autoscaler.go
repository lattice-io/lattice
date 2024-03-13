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

package autoscaler

import (
	"context"
	"fmt"
	"math"
	"strings"

	breezemlv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	"github.com/breezeml/lattice-operator/pkg/billing"
	trainingoperatorcommon "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/common"
	"github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/common/util"
	latticeconfig "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/config"
	"github.com/go-logr/logr"
	apiv1 "github.com/kubeflow/common/pkg/apis/common/v1"
	"github.com/kubeflow/common/pkg/core"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/meta"
	"k8s.io/apimachinery/pkg/api/resource"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/manager"
	"sigs.k8s.io/controller-runtime/pkg/source"
)

const (
	controllerName = "trainingjob-autoscaler"
)

func NewReconciler(mgr manager.Manager, billingDaemon *billing.Daemon, config *latticeconfig.LatticeConfig) *TrainingJobAutoScaler {
	r := &TrainingJobAutoScaler{
		Client:        mgr.GetClient(),
		Scheme:        mgr.GetScheme(),
		Recorder:      mgr.GetEventRecorderFor(controllerName),
		Reader:        mgr.GetAPIReader(),
		Log:           log.Log,
		BillingDaemon: billingDaemon,
		LatticeConfig: config,
	}

	return r
}

type TrainingJobAutoScaler struct {
	client.Client
	Scheme        *runtime.Scheme
	Log           logr.Logger
	Recorder      record.EventRecorder
	Reader        client.Reader
	BillingDaemon *billing.Daemon
	LatticeConfig *latticeconfig.LatticeConfig
}

//+kubebuilder:rbac:groups=breezeml.ai,resources=trainingjobs,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups=breezeml.ai,resources=trainingjobs/status,verbs=get;update;patch
//+kubebuilder:rbac:groups=breezeml.ai,resources=trainingjobs/finalizers,verbs=update
//+kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch;create;update;patch;delete
//+kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch;create;delete
//+kubebuilder:rbac:groups="",resources=nodes,verbs=get;list;watch
//+kubebuilder:rbac:groups="",resources=configmaps,verbs=get

func (r *TrainingJobAutoScaler) SetupWithManager(mgr ctrl.Manager) error {
	// Configure the manager to watch trainingjobs and let r reconciles them
	return ctrl.NewControllerManagedBy(mgr).
		Named(controllerName).
		For(&breezemlv1.TrainingJob{}).
		Watches(&source.Kind{Type: &corev1.Node{}}, &handler.EnqueueRequestForObject{}).
		Complete(r)
}

// UpdateJobStatusInApiServer updates the job status in to cluster.
func (r *TrainingJobAutoScaler) UpdateJobStatusInApiServer(job interface{}) error {
	trainingjob, ok := job.(*breezemlv1.TrainingJob)
	trainingoperatorcommon.ClearGeneratedFields(&trainingjob.ObjectMeta)
	if !ok {
		return fmt.Errorf("%+v is not a type of TrainingJob", job)
	}

	// We need to set up initial replica status if nil. Otherwise the cluster won't allow us to update
	if trainingjob.Status.ExecStatus.ReplicaStatuses == nil {
		core.InitializeReplicaStatuses(&trainingjob.Status.ExecStatus, breezemlv1.TrainingJobDefaultReplicaType)
	}

	result := r.Status().Update(context.Background(), trainingjob)

	if result != nil {
		r.Log.WithValues("trainingjob", types.NamespacedName{
			Namespace: trainingjob.GetNamespace(),
			Name:      trainingjob.GetName(),
		})
		return result
	}

	return nil
}

func (r *TrainingJobAutoScaler) GenLabels(jobName string) map[string]string {
	jobName = strings.Replace(jobName, "/", "-", -1)
	return map[string]string{
		// TODO(#149): Remove deprecated labels.
		apiv1.OperatorNameLabel: controllerName,
		apiv1.JobNameLabel:      jobName,
	}
}

// Get pods for the trainingjob
func (r *TrainingJobAutoScaler) GetPodsForJob(obj interface{}) ([]*corev1.Pod, error) {
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

// Get the number of specified resources
func (r *TrainingJobAutoScaler) getNumResources(ctx context.Context, resourceName corev1.ResourceName, jobNodeSelector *client.MatchingLabels) (int32, error) {
	var nodes corev1.NodeList
	if err := r.List(ctx, &nodes, *jobNodeSelector); err != nil {
		return int32(0), err
	}

	nRes := int32(0)
	for _, node := range nodes.Items {
		if resourceName == corev1.ResourceName(util.NodeResourceType) {
			nRes += int32(1)
		} else {
			quantity := node.Status.Allocatable.Name(resourceName, resource.DecimalSI)
			if val, ok := quantity.AsInt64(); ok {
				if val > math.MaxInt32 || val < math.MinInt32 {
					return int32(0), fmt.Errorf("the number of allocated resource is too large. we only support int32 range. ")
				}
				nRes += int32(val)
			}
		}
	}
	return nRes, nil
}

// Get the max cluster size
// (maximum number of workers that can run at the same time)
// Currently we assume each worker consume a single piece of resource (node or gpu)
func (r *TrainingJobAutoScaler) getTotalNumResources(
	ctx context.Context,
	req ctrl.Request,
	logger *logr.Logger,
	resourceName corev1.ResourceName,
) (int32, error) {

	var totalNumResources int32
	var valueErr error

	jobNodeSelector := r.LatticeConfig.JobNodeSelector

	if r.LatticeConfig.DebugWorldSize != nil {
		totalNumResources = *r.LatticeConfig.DebugWorldSize
	} else {
		totalNumResources, valueErr = r.getNumResources(ctx, resourceName, &jobNodeSelector)
	}

	return totalNumResources, valueErr
}

// Main reconcile function body
func (r *TrainingJobAutoScaler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	_ = log.FromContext(ctx)
	logger := r.Log.WithValues(breezemlv1.TrainingJobSingular, r.LatticeConfig.Namespace)

	// Get the resource unit name we schedule jobs with
	resourceName := r.LatticeConfig.ResourceUnit

	// Get the size of the cluster
	// If not manually set, we currently assume that we want to run one pod on one node
	totalNumResources, err := r.getTotalNumResources(ctx, req, &logger, resourceName)
	if err != nil {
		logger.Info(err.Error(), "Set world size to the number of nodes instead", req.NamespacedName.String())
	}

	// Fetch current jobs
	var trainingjobs breezemlv1.TrainingJobList
	err = r.List(ctx, &trainingjobs, client.InNamespace(r.LatticeConfig.Namespace))
	if err != nil {
		logger.Info(err.Error(), "Unable to fetch trainingjobs from the cluster", r.LatticeConfig.Namespace)
	}

	// If some fields are missing from the trainingjob, fill in the default values
	for i := range trainingjobs.Items {
		r.Scheme.Default(&trainingjobs.Items[i])
	}

	// Store current jobs
	origTrainingJobs := trainingjobs.DeepCopy()

	// Find and set correct status for completed jobs (succeeded or failed), newly created jobs, and jobs under cooldown
	err = util.ResetJobStatus(&trainingjobs)
	if err != nil {
		logger.Info(err.Error(), "Some trainingjob's status seems inconsistent. Please check earlier error messages", r.LatticeConfig.Namespace)
	}

	// Construct running list and waiting list
	var priorityList []*breezemlv1.TrainingJob
	var runningList []*breezemlv1.TrainingJob
	var waitingList []*breezemlv1.TrainingJob

	// Step 1: sort the jobs based on their priority and queueTime
	err = util.ConstructPriorityList(&trainingjobs, &priorityList, totalNumResources)
	if err != nil {
		logger.Info(err.Error(), "Failed to construct jobs based on their priority and queue time.", r.LatticeConfig.Namespace)
	}

	// Step 2: dispatch workers based on an ideal priority-FIFO scheduling algorithm
	err = util.DispatchWorkers(&priorityList, totalNumResources, resourceName)
	if err != nil {
		logger.Info(err.Error(), "Failed to dispatch workers to jobs.", r.LatticeConfig.Namespace)
	}

	// Step 3: adjustment of worker size, try to squeeze new jobs in to use more resources
	err = util.ConstructSchedulingLists(&priorityList, &runningList, &waitingList, totalNumResources)
	if err != nil {
		logger.Info(err.Error(), "Failed to construct running list and waiting list.", r.LatticeConfig.Namespace)
	}
	err = util.StartWaitingJobs(&runningList, &waitingList, totalNumResources, resourceName, &logger)
	if err != nil {
		logger.Info(err.Error(), "Some error occurs when starting waiting jobs.", r.LatticeConfig.Namespace)
	}

	// ========= Here HPA logic ends =========//
	// If we need to reconcile any jobs, we should have a valid license
	if !r.BillingDaemon.IsApproved() {
		logger.Error(fmt.Errorf("invalid license"), "failed to validate license")
		return ctrl.Result{Requeue: true, RequeueAfter: breezemlv1.LatticeDefaultRerunDuration}, nil
	}

	// Update prometheus metrics
	util.UpdatePrometheusMetrics(&trainingjobs, totalNumResources, resourceName)

	// Next, we update trainingjob.status based on the HPA result
	reconcileRerun := false
	// Reconcile jobs based on the ideal status
	// For each job, we generate replicaMap based on its intended status (job.Status)
	for idx := range trainingjobs.Items {
		trainingjob := &trainingjobs.Items[idx]

		// We check whether we have made a decision to autoscale a job (including start/stop).
		// If so, we need to make sure we we reset the timer to requeue the job.
		if util.TrainingJobAutoscaled(&origTrainingJobs.Items[idx], trainingjob) {
			trainingjob.Status.RequeueTime = nil
		}

		if err := r.UpdateJobStatusInApiServer(trainingjob); err != nil {
			logger.Info(err.Error(), "Unable to update the job in the cluster. Will try again.", trainingjob.Name)
			reconcileRerun = true
			continue
		}
	}

	// If we failed to update a job, we should rerun the autoscaler later
	if reconcileRerun {
		return ctrl.Result{Requeue: true, RequeueAfter: breezemlv1.LatticeDefaultRerunDuration}, nil
	}

	// If there is a job under cooldown, we need to schedule a re-run for it
	cooldownRerun, nearestCooldown := util.FindRerunTimeForCooldownJob(&trainingjobs)
	if cooldownRerun {
		return ctrl.Result{Requeue: true, RequeueAfter: nearestCooldown}, nil
	}

	return ctrl.Result{}, nil
}
