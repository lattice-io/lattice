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

package reconciler

import (
	"context"
	"fmt"
	"time"

	breezemlv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	"github.com/breezeml/lattice-operator/pkg/billing"
	trainingoperatorcommon "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/common"
	"github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/common/util"
	latticeconfig "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/config"
	"github.com/go-logr/logr"
	commonv1 "github.com/kubeflow/common/pkg/apis/common/v1"
	"github.com/kubeflow/common/pkg/controller.v1/common"
	"github.com/kubeflow/common/pkg/controller.v1/control"
	"github.com/kubeflow/common/pkg/controller.v1/expectation"
	commonutil "github.com/kubeflow/common/pkg/util"
	"github.com/sirupsen/logrus"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/equality"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	"k8s.io/client-go/informers"
	kubeclientset "k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/record"
	"k8s.io/utils/pointer"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/event"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/manager"
	"sigs.k8s.io/controller-runtime/pkg/predicate"
	"sigs.k8s.io/controller-runtime/pkg/source"
)

const (
	controllerName = "trainingjob-reconciler"
)

func NewReconciler(mgr manager.Manager, billingDaemon *billing.Daemon, config *latticeconfig.LatticeConfig) *TrainingJobReconciler {
	r := &TrainingJobReconciler{
		Client:        mgr.GetClient(),
		Scheme:        mgr.GetScheme(),
		Recorder:      mgr.GetEventRecorderFor(controllerName),
		Reader:        mgr.GetAPIReader(),
		Log:           log.Log,
		BillingDaemon: billingDaemon,
		LatticeConfig: config,
	}

	// Create clients
	cfg := mgr.GetConfig()
	kubeClientSet := kubeclientset.NewForConfigOrDie(cfg)
	sharedInformers := informers.NewSharedInformerFactory(kubeClientSet, 0)
	priorityClassInformer := sharedInformers.Scheduling().V1().PriorityClasses()

	// Initialize common job controller
	r.JobController = common.JobController{
		Controller:                  r,
		Expectations:                expectation.NewControllerExpectations(),
		Config:                      common.JobControllerConfiguration{},
		WorkQueue:                   &util.FakeWorkQueue{},
		Recorder:                    r.Recorder,
		KubeClientSet:               kubeClientSet,
		PriorityClassLister:         priorityClassInformer.Lister(),
		PriorityClassInformerSynced: priorityClassInformer.Informer().HasSynced,
		PodControl:                  control.RealPodControl{KubeClient: kubeClientSet, Recorder: r.Recorder},
		ServiceControl:              control.RealServiceControl{KubeClient: kubeClientSet, Recorder: r.Recorder},
	}

	gangSchedulingSetupFunc := common.GenNonGangSchedulerSetupFunc()
	gangSchedulingSetupFunc(&r.JobController)

	return r
}

type TrainingJobReconciler struct {
	common.JobController
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
//+kubebuilder:rbac:groups="",resources=configmaps,verbs=get

func (r *TrainingJobReconciler) SetupWithManager(mgr ctrl.Manager) error {
	c, err := controller.New(r.ControllerName(), mgr, controller.Options{
		Reconciler: r,
	})

	if err != nil {
		return err
	}

	// using onOwnerCreateFunc is easier to set defaults
	if err = c.Watch(&source.Kind{Type: &breezemlv1.TrainingJob{}}, &handler.EnqueueRequestForObject{},
		predicate.Funcs{CreateFunc: r.onOwnerCreateFunc()},
	); err != nil {
		return err
	}

	// inject watching for job related pod
	if err = c.Watch(&source.Kind{Type: &corev1.Pod{}}, &handler.EnqueueRequestForOwner{
		IsController: true,
		OwnerType:    &breezemlv1.TrainingJob{},
	}, predicate.Funcs{
		CreateFunc: util.OnDependentCreateFunc(r.Expectations),
		UpdateFunc: util.OnDependentUpdateFunc(&r.JobController),
		DeleteFunc: util.OnDependentDeleteFunc(r.Expectations),
	}); err != nil {
		return err
	}

	// inject watching for job related service
	if err = c.Watch(&source.Kind{Type: &corev1.Service{}}, &handler.EnqueueRequestForOwner{
		IsController: true,
		OwnerType:    &breezemlv1.TrainingJob{},
	}, predicate.Funcs{
		CreateFunc: util.OnDependentCreateFunc(r.Expectations),
		UpdateFunc: util.OnDependentUpdateFunc(&r.JobController),
		DeleteFunc: util.OnDependentDeleteFunc(r.Expectations),
	}); err != nil {
		return err
	}

	return nil
}

// onOwnerCreateFunc modify creation condition.
func (r *TrainingJobReconciler) onOwnerCreateFunc() func(event.CreateEvent) bool {
	return func(e event.CreateEvent) bool {
		trainingjob, ok := e.Object.(*breezemlv1.TrainingJob)

		running_pod := int32(0) // current running pods for the job
		for _, v := range trainingjob.Status.ExecStatus.ReplicaStatuses {
			running_pod += v.Active
		}

		if !ok {
			return true
		}
		r.Scheme.Default(trainingjob)
		trainingoperatorcommon.CreatedJobsCounterInc(trainingjob.Namespace, breezemlv1.TrainingJobFrameworkName)

		return true
	}
}

func (r *TrainingJobReconciler) ControllerName() string {
	return controllerName
}

func (r *TrainingJobReconciler) GetAPIGroupVersion() schema.GroupVersion {
	return breezemlv1.GroupVersion
}

func (r *TrainingJobReconciler) GetAPIGroupVersionKind() schema.GroupVersionKind {
	return breezemlv1.GroupVersion.WithKind(breezemlv1.TrainingJobKind)
}

func (r *TrainingJobReconciler) GetDefaultContainerName() string {
	return breezemlv1.TrainingJobDefaultContainerName
}

func (r *TrainingJobReconciler) GetDefaultContainerPortName() string {
	return breezemlv1.TrainingJobDefaultContainerPortName
}

func (r *TrainingJobReconciler) GetGroupNameLabelValue() string {
	return breezemlv1.GroupVersion.Group
}

func (r *TrainingJobReconciler) GetJobFromAPIClient(namespace, name string) (metav1.Object, error) {
	job := &breezemlv1.TrainingJob{}
	err := r.Reader.Get(context.Background(), types.NamespacedName{Namespace: namespace, Name: name}, job)

	if err != nil {
		if errors.IsNotFound(err) {
			logrus.Error(err, "lattice job not found", "namespace", namespace, "name", name)
		} else {
			logrus.Error(err, "failed to get job from api-server", "namespace", namespace, "name", name)
		}
		return nil, err
	}
	return job, nil
}

func (r *TrainingJobReconciler) GetJobFromInformerCache(namespace, name string) (metav1.Object, error) {
	job := &breezemlv1.TrainingJob{}
	err := r.Get(context.Background(), types.NamespacedName{Namespace: namespace, Name: name}, job)

	if err != nil {
		if errors.IsNotFound(err) {
			logrus.Error(err, "lattice job not found", "namespace", namespace, "name", name)
		} else {
			logrus.Error(err, "failed to get job from api-server", "namespace", namespace, "name", name)
		}
		return nil, err
	}
	return job, nil
}

// SetClusterSpec sets the cluster spec and init container for the pod
func (r *TrainingJobReconciler) SetClusterSpec(job interface{}, podTemplate *corev1.PodTemplateSpec, rtype, index string) error {
	// TODO commented out since setPodEnv and SetInitContainer have not been implemented
	//if err := setPodEnv(job, podTemplate, rtype, index); err != nil {
	//	return err
	//}
	//if err := setInitContainer(job, podTemplate, rtype, index, r.Log); err != nil {
	//	return err
	//}
	return nil
}

// UpdateJobStatus updates the job status and job conditions
func (r *TrainingJobReconciler) UpdateJobStatus(job interface{},
	replicas map[commonv1.ReplicaType]*commonv1.ReplicaSpec,
	jobStatus *commonv1.JobStatus) error {

	trainingjob, ok := job.(*breezemlv1.TrainingJob)
	if !ok {
		return fmt.Errorf("%+v is not a type of TrainingJob", job)
	}

	trainingjobKey, err := common.KeyFunc(trainingjob)
	if err != nil {
		utilruntime.HandleError(fmt.Errorf("couldn't get key for trainingjob object %#v: %v", trainingjob, err))
		return err
	}

	logger := commonutil.LoggerForJob(trainingjob)

	// Set StartTime.
	if jobStatus.StartTime == nil {
		now := metav1.Now()
		jobStatus.StartTime = &now
		// enqueue a sync to check if job past ActiveDeadlineSeconds
		if trainingjob.Spec.RunPolicy.ActiveDeadlineSeconds != nil {
			logger.Infof("Job with ActiveDeadlineSeconds will sync after %d seconds", *trainingjob.Spec.RunPolicy.ActiveDeadlineSeconds)
			r.WorkQueue.AddAfter(trainingjobKey, time.Duration(*trainingjob.Spec.RunPolicy.ActiveDeadlineSeconds)*time.Second)
		}
	}

	for rtype, spec := range replicas {
		status := jobStatus.ReplicaStatuses[rtype]
		status.Selector = metav1.FormatLabelSelector(r.GenLabelSelector(trainingjob.Name, rtype))

		succeeded := status.Succeeded
		expected := *(spec.Replicas) - succeeded
		running := status.Active
		failed := status.Failed
		specReplicas := *spec.Replicas

		logrus.Infof("TrainingJob=%s, ReplicaType=%s expected=%d, running=%d, succeeded=%d, failed=%d, Replicas=%d",
			trainingjob.Name, rtype, expected, running, succeeded, failed, specReplicas)

		// There shouldn't be a master since lattice agent is handling it.
		// We implicitly assume all specs are workers.
		if expected == 0 && succeeded > 0 {
			msg := fmt.Sprintf("TrainingJob %s/%s successfully completed.",
				trainingjob.Namespace, trainingjob.Name)
			r.Recorder.Event(trainingjob, corev1.EventTypeNormal, commonutil.JobSucceededReason, msg)
			if jobStatus.CompletionTime == nil {
				now := metav1.Now()
				jobStatus.CompletionTime = &now
			}
			err := commonutil.UpdateJobConditions(jobStatus,
				commonv1.JobSucceeded, commonutil.JobSucceededReason, msg)
			if err != nil {
				commonutil.LoggerForJob(trainingjob).Infof("Append trainingjob condition error: %v", err)
				return err
			}
			trainingoperatorcommon.SuccessfulJobsCounterInc(trainingjob.Namespace, breezemlv1.TrainingJobFrameworkName)
			util.CompleteJob(trainingjob)
		} else if running > 0 {
			// Some workers are still running, leave a running condition.
			msg := fmt.Sprintf("TrainingJob %s/%s is running.",
				trainingjob.Namespace, trainingjob.Name)
			err := commonutil.UpdateJobConditions(jobStatus, commonv1.JobRunning, commonutil.JobRunningReason, msg)
			if err != nil {
				commonutil.LoggerForJob(trainingjob).Infof("Append trainingjob condition error: %v", err)
				return err
			}
		}

		if failed > 0 && (specReplicas > succeeded+running) {
			if spec.RestartPolicy != commonv1.RestartPolicyNever {
				msg := fmt.Sprintf("TrainingJob %s is restarting because %d %s replica(s) failed.", trainingjob.Name, failed, rtype)
				r.Recorder.Event(trainingjob, corev1.EventTypeWarning, commonutil.JobRestartingReason, msg)
				err := commonutil.UpdateJobConditions(jobStatus, commonv1.JobRestarting, commonutil.JobRestartingReason, msg)
				if err != nil {
					commonutil.LoggerForJob(trainingjob).Infof("Append job condition error: %v", err)
					return err
				}
				trainingoperatorcommon.RestartedJobsCounterInc(trainingjob.Namespace, breezemlv1.TrainingJobFrameworkName)
			} else {
				msg := fmt.Sprintf("TrainingJob %s is failed because %d %s replica(s) failed.", trainingjob.Name, failed, rtype)
				r.Recorder.Event(trainingjob, corev1.EventTypeNormal, commonutil.JobFailedReason, msg)
				if trainingjob.Status.ExecStatus.CompletionTime == nil {
					now := metav1.Now()
					trainingjob.Status.ExecStatus.CompletionTime = &now
				}
				err := commonutil.UpdateJobConditions(jobStatus, commonv1.JobFailed, commonutil.JobFailedReason, msg)
				if err != nil {
					commonutil.LoggerForJob(trainingjob).Infof("Append job condition error: %v", err)
					return err
				}
				trainingoperatorcommon.FailedJobsCounterInc(trainingjob.Namespace, breezemlv1.TrainingJobFrameworkName)
				util.CompleteJob(trainingjob)
			}
		}
	}

	return nil
}

// UpdateJobStatusInApiServer updates the job status in to cluster.
func (r *TrainingJobReconciler) UpdateJobStatusInApiServer(job interface{}, jobStatus *commonv1.JobStatus) error {
	if jobStatus.ReplicaStatuses == nil {
		jobStatus.ReplicaStatuses = map[commonv1.ReplicaType]*commonv1.ReplicaStatus{}
	}

	trainingjob, ok := job.(*breezemlv1.TrainingJob)
	trainingoperatorcommon.ClearGeneratedFields(&trainingjob.ObjectMeta)
	if !ok {
		return fmt.Errorf("%+v is not a type of TrainingJob", job)
	}

	// Job status passed in differs with status in job, update in basis of the passed in one.
	if !equality.Semantic.DeepEqual(&trainingjob.Status, jobStatus) {
		trainingjob = trainingjob.DeepCopy()
		trainingjob.Status.ExecStatus = *jobStatus.DeepCopy()
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

func (jc *TrainingJobReconciler) GenLabelSelector(jobName string,
	rtype commonv1.ReplicaType) *metav1.LabelSelector {
	labels := jc.GenLabels(jobName)
	labels[commonv1.ReplicaTypeLabel] = string(rtype)

	return &metav1.LabelSelector{
		MatchLabels: labels,
	}
}

func (r *TrainingJobReconciler) DeleteJob(job interface{}) error {
	trainingjob, ok := job.(*breezemlv1.TrainingJob)
	if !ok {
		return fmt.Errorf("%+v is not a type of TrainingJob", job)
	}
	if err := r.Delete(context.Background(), trainingjob); err != nil {
		r.Recorder.Eventf(trainingjob, corev1.EventTypeWarning, control.FailedDeletePodReason, "Error deleting: %v", err)
		logrus.Error(err, "failed to delete job", "namespace", trainingjob.Namespace, "name", trainingjob.Name)
		return err
	}
	r.Recorder.Eventf(trainingjob, corev1.EventTypeNormal, control.SuccessfulDeletePodReason, "Deleted job: %v", trainingjob.Name)
	logrus.Info("job deleted", "namespace", trainingjob.Namespace, "name", trainingjob.Name)
	return nil
}

func (r *TrainingJobReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	_ = log.FromContext(ctx)
	logger := r.Log.WithValues(breezemlv1.TrainingJobSingular, req.NamespacedName)

	trainingjob := &breezemlv1.TrainingJob{}
	err := r.Get(ctx, req.NamespacedName, trainingjob)
	if err != nil {
		// The trainingjob has been deleted. We delete the prometheus metric as well
		trainingoperatorcommon.RunningPodsGaugeDeleteMetric(req.Namespace, req.Name)
		logger.Info(err.Error(), "unable to fetch TrainingJob", req.NamespacedName.String())
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	pods, err := r.Controller.GetPodsForJob(trainingjob)
	// Update the number of running pods before reconcilation (prometheus)
	trainingoperatorcommon.RunningPodsGaugeSetValue(trainingjob.Namespace, trainingjob.Name, util.NumRunningPods(pods))

	if err != nil {
		logger.Info(err.Error(), "Unable to get pod information for the job.", trainingjob.Name)
	}

	// Sometimes kubeflow throws an error if we try to rescale a job when some of its pods are terminating
	// To solve this issue, we detect whether all pods are ready. If not, we do not touch the job this time,
	// but schedule a rerun of the reconcilation.

	allPodsReady := util.AllPodsReady(pods)
	if !allPodsReady && trainingjob.Status.Stage == breezemlv1.TrainingJobStageRunning {
		if trainingjob.Status.RequeueTime == nil {
			// we need to start the timer, and update the timer to the cluster
			dueTime := metav1.NewTime(metav1.Now().Time.Add(breezemlv1.LatticeDefaultScheduleFailureDuration))
			trainingjob.Status.RequeueTime = &dueTime
			if err := r.UpdateJobStatusInApiServer(trainingjob, &trainingjob.Status.ExecStatus); err != nil {
				utilruntime.HandleError(err)
			}
		}

		// if the number of pod is expected to be the same as the current size, we will wait for the pods to be ready if due time is not reached
		if len(pods) == int(trainingjob.Status.CurrentSize) {
			now := metav1.Now()
			if now.After(trainingjob.Status.RequeueTime.Time) {
				// We won't try to wait anymore. We'll requeue the job
				cooldownTime := metav1.NewTime(now.Add(breezemlv1.LatticeDefaultCooldownDuration))
				util.RequeueJob(trainingjob, &cooldownTime)
				if err := r.UpdateJobStatusInApiServer(trainingjob, &trainingjob.Status.ExecStatus); err != nil {
					utilruntime.HandleError(err)
				}
				logger.Info("Pause a job due to pod schedule/start failure", "name", req.NamespacedName.String())
			} else {
				// we should skip this round of reconcilation, and wait for the next one
				logger.Info("Will wait for an additional amount of time for job", "name", req.NamespacedName.String())
				return ctrl.Result{Requeue: true, RequeueAfter: breezemlv1.LatticeDefaultRerunDuration}, nil
			}
		}

		// otherwise, we will need to do reconcilation to make sure the number of pods is correct
		logger.Info("Some pods are not ready, but we will still run reconcilation since the number of pods is incorrect", "name", req.NamespacedName.String())
	} else {
		// all pods are ready. We won't try to requeue the job anymore
		logger.Info("Job not running or has all pods ready. Would not try to requeue it", "name", req.NamespacedName.String())
		trainingjob.Status.RequeueTime = nil
	}

	msg := fmt.Sprintf("Reconciling job %s (stage: %s) to size: %d", trainingjob.Name, trainingjob.Status.Stage, trainingjob.Status.CurrentSize)
	r.Recorder.Event(trainingjob, corev1.EventTypeNormal, commonutil.JobRunningReason, msg)

	jobKey, err := common.KeyFunc(trainingjob)
	if err != nil {
		utilruntime.HandleError(fmt.Errorf("couldn't get jobKey for job object %#v: %v", trainingjob, err))
	}

	if trainingjob.Spec.ReplicaSpecs.Replicas == nil {
		trainingjob.Spec.ReplicaSpecs.Replicas = pointer.Int32(0)
	}

	if trainingjob.Status.Stage == breezemlv1.TrainingJobStageRunning {
		*trainingjob.Spec.ReplicaSpecs.Replicas = trainingjob.Status.CurrentSize
	} else {
		*trainingjob.Spec.ReplicaSpecs.Replicas = int32(0)
	}

	replicaMap := map[commonv1.ReplicaType]*commonv1.ReplicaSpec{
		breezemlv1.TrainingJobDefaultReplicaType: trainingjob.Spec.ReplicaSpecs,
	}

	replicaTypes := util.GetReplicaTypes(replicaMap)
	needReconcile := util.SatisfiedExpectations(r.Expectations, jobKey, replicaTypes)

	if *trainingjob.Spec.ReplicaSpecs.Replicas == int32(0) && len(pods) == 0 {
		// There is a bug in kubeflow/common/pkg/controller.v1/common/pod.go:ReconcilePods.
		// When resizing from 0 to 0, it creates a single pod.
		// In the current implementation, we ignore "resizing to 0" since we never stop a running job.
		// However, going forward, we may want preemptive behaviors, allowing high priority jobs stopping lower ones.
		// TODO: At that time, we need to reimplement Reconcile logics in kubeflow/common in our repo.
		return ctrl.Result{}, nil
	}

	if !needReconcile || trainingjob.GetDeletionTimestamp() != nil {
		logger.Info("reconcile cancelled, job does not need to do reconcile or has been deleted",
			"sync", needReconcile, "deleted", trainingjob.GetDeletionTimestamp() != nil)
	}

	// Set default priorities to lattice job
	r.Scheme.Default(trainingjob)

	// Prepend command with Lattice Installer and Agent if needed
	if *trainingjob.Spec.InjectLattice {
		if err := util.WrapEntrypoint(trainingjob, r.LatticeConfig); err != nil {
			logrus.Error(err)
		}
	}

	// If jobNodeSelector is specified, we should apply it to the job
	jobNodeSelector := r.LatticeConfig.JobNodeSelector
	util.WrapJobNodeSelector(trainingjob, &jobNodeSelector)

	err = r.ReconcileJobs(trainingjob, replicaMap, trainingjob.Status.ExecStatus, &trainingjob.Spec.RunPolicy)
	if err != nil {
		logger.Error(err, "Reconcile TrainingJob error")
	}

	// Update the number of running pods after reconcilation (prometheus)
	trainingoperatorcommon.RunningPodsGaugeSetValue(trainingjob.Namespace, trainingjob.Name, util.NumRunningPods(pods))

	return ctrl.Result{}, nil
}
